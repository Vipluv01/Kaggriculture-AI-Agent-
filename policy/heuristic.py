"""Rule-based Kaggriculture agent.

v2: farmer + hired hands each patrol their own band of tiles in a snake
pattern; at each tile: harvest if ripe, water if thirsty, else plant the
target crop if seed is held. TOMATO is the default crop: moderate seed cost
(50), ongoing yield (produces repeatedly once mature) beats a one-shot crop
like the "starter" baseline's CARROT loop once several tiles are in rotation.

Hands are re-hired every day (the env wipes farm["hands"] and resets the
Fibonacci hire-cost counter at end-of-day) so the agent hires HANDS_CAP fresh
hands each morning (hour 0) -- cheap, since the first few hires of a day cost
$1-3 each.

Land expansion was tried twice and dropped both times: v1 bought land
without buying labor to work it (lost money net -- unwatered tiles turn to
weeds, wasting seed cost). A follow-up attempt paired land with
quadrant-scaled hiring and fixed a cash-reserve bug (it kept hiring even at
near-zero money, starving out seed restocking), but even the fixed version
scored lower than staying in the single starting quadrant with hands maxed
out (~$5.2-5.4k vs ~$6.2-6.5k final money over 10 episodes each, see
README): the market's price decays with supply (TOMATO's curve saturates
around 200 units/24 days) and land capex doesn't pay back inside a 30-day
season. Left as a documented dead end, not a TODO.
"""

TARGET_CROP = "TOMATO"
HANDS_CAP = 4  # hands hired per day -> up to 5 total workers (farmer + hands)
SEED_BUFFER_PER_WORKER = 2
# TOMATO: first_yield_day=8, interval=1, max_yield=4 production ticks (env
# defaults) -- after day planted_day + 8 + (4-1)*1 = +11, all 4 ticks are
# used up and the tile produces nothing more, ever; left alone it just
# decays into a weed. Dig it at that point and replant instead of wasting
# the tile.
TOMATO_EXHAUST_AGE = 8 + (4 - 1) * 1


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
            if t.get("yield_units", 0) > 0:
                return x, y, "ripe"
            if not t.get("watered_today", False):
                return x, y, "thirsty"
            age = day - t.get("planted_day", day)
            if age >= TOMATO_EXHAUST_AGE:
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
    if have < seed_target and money >= 50:
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
