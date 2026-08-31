"""Rule-based Kaggriculture agent.

v4: farmer + hired hands each patrol their own band of tiles in a snake
pattern; at each tile: harvest if ripe, water if thirsty, dig if spent/weed,
else plant the target crop if seed is held.

Crop choice was the single biggest lever found: MELON ($250 base price, one
shot, max_yield=6) beats TOMATO ($60 base price, ongoing, max_yield=4) by
more than 3x in final money (~$27k vs ~$8k), even though both crops cap out
at a similar few-units-per-tile yield -- MELON's per-unit price dominates.
Reaching that number required fixing a real correctness bug along the way:
a one-shot crop starts at yield_units=1 immediately on planting (see
kaggriculture.py's _new_plant), so the "ripe" check has to also gate on
age >= first_yield_day, or the agent wastes every turn on a HARVEST the env
silently no-ops until maturity instead of watering for the bonus-yield
window.

Hands are re-hired every day (the env wipes farm["hands"], the farmer's
position, carried inventories, and hire cost at end-of-day) so the agent
hires HANDS_CAP fresh hands each morning (hour 0) -- cheap, since the first
few hires of a day cost $1-3 each.

Two things tried and dropped, both documented so they don't get
re-litigated without new evidence:
- Land expansion (twice): v1 bought land without buying labor to work it
  (lost money net -- unwatered tiles turn to weeds, wasting seed cost). A
  follow-up paired land with quadrant-scaled hiring and fixed a real
  cash-reserve bug (it kept hiring even at near-zero money, starving out
  seed restocking), but even fixed it scored lower than staying in the
  single starting quadrant with hands maxed: the market's price decays with
  supply and land capex doesn't pay back inside a 30-day season.
- Fertilizer: buy it, have a worker fetch it from the shed and apply it.
  Implemented correctly (including fixing a bug where the generic "sell
  everything in the shed" loop was reselling the fertilizer before any
  worker could pick it up) -- but re-reading kaggriculture.py showed the
  fertilizer bonus is capped by the same `min(max_yield, ...)` as ordinary
  production: it only reaches the yield cap *faster*, it never raises the
  cap. Confirmed net-negative once travel/purchase overhead is counted.
"""

TARGET_CROP = "MELON"
HANDS_CAP = 6  # hands hired per day -> up to 7 total workers (farmer + hands).
# Swept 2/4/6/8 for MELON: results were close (~26.3-27.1k) and not
# monotonic -- MELON's economics (labor mostly idles during the 10-12 day
# pre-harvest dry spell, then a couple of huge lump-sum harvests) make labor
# count matter far less than for TOMATO. 6 scored best of those tested.
SEED_BUFFER_PER_WORKER = 2

# Mirrors kaggle_environments' CROPS table (kaggriculture.py) for the two
# crops this agent knows how to farm -- kept local since the submission
# can't import the env package.
#   ongoing crops (TOMATO) produce repeated small ticks and start at
#   yield_units=0, so "yield_units > 0" alone means ripe.
#   one-shot crops (MELON) start at yield_units=1 immediately on planting
#   (see kaggriculture.py's _new_plant), so a naive "yield_units > 0" check
#   fires HARVEST from turn 1 -- the env silently no-ops that until
#   first_yield_day, but every turn wasted on a failing HARVEST is a turn
#   not spent watering for the bonus-yield window. Ripe must also gate on
#   age >= first_yield_day for these.
CROP_INFO = {
    "TOMATO": {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "MELON": {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}
_CROP = CROP_INFO[TARGET_CROP]
# Ongoing crops only: after this age all production ticks are used up and
# the tile produces nothing more, ever -- left alone it decays into a weed.
# Dig it at that point and replant instead of wasting the tile. (One-shot
# crops don't need this: HARVEST clears the tile automatically.)
CROP_EXHAUST_AGE = _CROP["first_yield_day"] + (_CROP["max_yield"] - 1) * max(1, _CROP["interval"])


def _snake_positions(size):
    for y in range(size):
        row = range(size) if y % 2 == 0 else range(size - 1, -1, -1)
        for x in row:
            yield x, y


def _workable_positions(tiles):
    size = len(tiles)
    return [(x, y) for x, y in _snake_positions(size) if tiles[y][x] != "LOCKED"]


def _band_for_worker(positions, worker_idx, num_workers):
    if not positions:
        return []
    chunk = max(1, len(positions) // num_workers)
    start = worker_idx * chunk
    end = len(positions) if worker_idx == num_workers - 1 else start + chunk
    return positions[start:end]


def _next_target_in_band(tiles, band, px, py, day):
    if not band:
        return px, py, "none"
    start = band.index((px, py)) if (px, py) in band else 0
    ordered = band[start:] + band[:start]
    for x, y in ordered:
        t = tiles[y][x]
        if t is None:
            return x, y, "empty"
        if isinstance(t, dict) and t.get("kind") == "WEED":
            return x, y, "weed"
        if isinstance(t, dict) and t.get("kind") == "PLANT":
            age = day - t.get("planted_day", day)
            mature = _CROP["ongoing"] or age >= _CROP["first_yield_day"]
            if mature and t.get("yield_units", 0) > 0:
                return x, y, "ripe"
            if not t.get("watered_today", False):
                return x, y, "thirsty"
            if _CROP["ongoing"] and age >= CROP_EXHAUST_AGE:
                # Fully spent -- all production ticks already used up, it'll
                # just decay into a weed if left alone. Clear it to replant.
                return x, y, "spent"
    return band[0][0], band[0][1], "none"


def _step_toward(fx, fy, tx, ty):
    if fx < tx:
        return "EAST"
    if fx > tx:
        return "WEST"
    if fy < ty:
        return "SOUTH"
    if fy > ty:
        return "NORTH"
    return None


def _worker_action(tiles, band, pos, seeds_available, day):
    px, py = pos
    tx, ty, state = _next_target_in_band(tiles, band, px, py, day)
    if (px, py) == (tx, ty):
        if state == "ripe":
            return ["HARVEST"]
        if state == "thirsty":
            return ["WATER"]
        if state in ("spent", "weed"):
            return ["DIG"]
        if state == "empty" and seeds_available:
            return ["PLANT", TARGET_CROP]
        return ["PASS"]
    move = _step_toward(px, py, tx, ty)
    return [move] if move else ["PASS"]


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def agent(obs):
    farms = obs.get("farms", [])
    player = obs.get("player", 0)
    private = obs.get("private", {}) or {}
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}

    farm = farms[player]
    fx, fy = farm["farmer"]
    tiles = farm["tiles"]
    money = farm["money"]
    hour = obs.get("hour", 0)
    hires_today = farm.get("hires_today", 0)
    seeds = private.get("seeds", {})
    shed = private.get("shed", {})
    hand_positions = [tuple(p) for p in farm.get("hands", [])]
    num_workers = 1 + len(hand_positions)

    market = []

    # Re-hire the day's hands at the very start of the day -- cheap (first
    # few hires cost $1-3) since the env wipes hands and hire cost at EOD.
    if hour == 0:
        n = hires_today
        budget = money * 0.5  # never spend more than half the morning's cash on labor
        spent = 0
        hired = 0
        while hired < HANDS_CAP:
            cost = _fib(n)
            if spent + cost > budget:
                break
            spent += cost
            n += 1
            hired += 1
        market.extend([["HIRE"]] * hired)

    for item, qty in shed.items():
        if qty > 0:
            market.append(["SELL", item, qty])

    seed_target = max(1, num_workers) * SEED_BUFFER_PER_WORKER
    have = seeds.get(TARGET_CROP, 0)
    if have < seed_target and money >= _CROP["seed"]:
        market.append(["BUY_SEED", TARGET_CROP, seed_target - have])

    market = market[:10]

    day = obs.get("day", 0)
    positions = _workable_positions(tiles)
    farmer_band = _band_for_worker(positions, 0, num_workers)
    seeds_available = seeds.get(TARGET_CROP, 0) > 0
    farmer_action = _worker_action(tiles, farmer_band, (fx, fy), seeds_available, day)

    hands_actions = []
    for i, hp in enumerate(hand_positions, start=1):
        band = _band_for_worker(positions, i, num_workers)
        hands_actions.append(_worker_action(tiles, band, hp, seeds_available, day))

    return {"farmer": farmer_action, "hands": hands_actions, "market": market}
