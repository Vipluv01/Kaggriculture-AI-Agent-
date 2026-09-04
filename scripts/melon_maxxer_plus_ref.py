"""An enhanced "Melon Maxxer" -- the tutorial's reference bot
(melon_maxxer_ref.py) extended with hired hands, so we can stress-test our
own agent against a MUCH higher-volume MELON competitor than the tutorial's
single-farmer version. Not a claim about what real ladder opponents do --
just a way to check whether our own MELON-heavy strategy stays robust if
someone else is also producing MELON at real scale into the same shared
market, since melon_maxxer_ref.py's single farmer never produces enough to
meaningfully test that.

Everything else about the naive strategy is left alone (still single-crop
MELON only, still dumps its whole shed at the sell threshold, no land
expansion, no diversification) -- only the labor-scaling weakness the
tutorial itself calls out ("it never hires farm hands") is fixed, so this
isolates the effect of MORE VOLUME specifically."""

from kaggle_environments.envs.kaggriculture.kaggriculture import CROPS

MELON_SEED_COST = CROPS["MELON"]["seed"]
MELON_MAX_YIELD_DAY = CROPS["MELON"]["max_yield_day"]
SELL_THRESHOLD = 0  # always sell -- the tutorial's $200 gate turned out to
# make melon_maxxer_plus never sell at all once our own volume had already
# depressed the shared price (measured: 0 units sold across a full game
# with 5 hands hired) -- not a useful stress test if the "competitor"
# never actually competes for the market. Dropping the gate makes it
# actually inject volume, which is the point of this variant.
HANDS_TARGET = 5  # modest -- enough to meaningfully scale MELON volume


def _step_toward(fx, fy, tx, ty):
    if fx > tx:
        return "WEST"
    if fx < tx:
        return "EAST"
    if fy > ty:
        return "NORTH"
    if fy < ty:
        return "SOUTH"
    return None


def _find_target_tile(farm, board_size, have_seed, px, py, taken):
    candidates = []
    for y in range(board_size):
        for x in range(board_size):
            if (x, y) in taken:
                continue
            tile = farm["tiles"][y][x]
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile["crop"] == "MELON":
                purpose = None
                if tile["yield_units"] > 0:
                    purpose = "harvest"
                if not tile["watered_today"]:
                    purpose = "water" if purpose is None else purpose
                if purpose:
                    candidates.append((x, y, purpose))
            elif tile is None and have_seed:
                candidates.append((x, y, "plant"))

    if not candidates:
        return None

    priority = {"harvest": 0, "water": 1, "plant": 2}
    candidates.sort(key=lambda c: (priority[c[2]], abs(c[0] - px) + abs(c[1] - py)))
    return candidates[0]


def _worker_action(farm, board_size, pos, seeds_available, taken, day):
    px, py = pos
    tile = farm["tiles"][py][px]
    if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile["crop"] == "MELON":
        age = day - tile["planted_day"]
        # Matches melon_maxxer_ref.py's farmer logic: HARVEST is a silent
        # no-op in the env until age >= MELON_MAX_YIELD_DAY, regardless of
        # yield_units (which is already 1 from the moment of planting for
        # one-shot crops) -- missing this gate the first time round meant
        # every HARVEST attempt was rejected and nothing ever reached the
        # shed (confirmed: 1031 HARVEST actions, 0 units ever sold).
        if age >= MELON_MAX_YIELD_DAY and tile["yield_units"] > 0:
            return ["HARVEST"]
        if not tile["watered_today"]:
            return ["WATER"]
    elif tile is None and seeds_available:
        return ["PLANT", "MELON"]
    target = _find_target_tile(farm, board_size, seeds_available, px, py, taken)
    if target:
        taken.add((target[0], target[1]))
        step = _step_toward(px, py, target[0], target[1])
        if step:
            return [step]
    return ["PASS"]


def melon_maxxer_plus(obs):
    farms = obs.get("farms", [])
    player = obs.get("player", 0)
    private = obs.get("private", {}) or {}
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}

    farm = farms[player]
    board_size = len(farm["tiles"])
    fx, fy = farm["farmer"]
    hand_positions = [tuple(p) for p in farm.get("hands", [])]
    hires_today = farm.get("hires_today", 0)
    day = obs.get("day", 0)

    seeds = private.get("seeds", {})
    shed = private.get("shed", {})
    market_prices = (obs.get("market", {}) or {}).get("prices", {})
    melon_price = market_prices.get("MELON", 0)

    market = []

    melons_in_shed = shed.get("MELON", 0)
    if melons_in_shed > 0 and melon_price >= SELL_THRESHOLD:
        market.append(["SELL", "MELON", melons_in_shed])

    have_seed = seeds.get("MELON", 0) > 0
    num_workers = 1 + len(hand_positions)
    if not have_seed and farm["money"] >= MELON_SEED_COST:
        market.append(["BUY_SEED", "MELON", max(1, num_workers)])

    if hires_today < HANDS_TARGET:
        market.extend([["HIRE"]] * (HANDS_TARGET - hires_today))

    market = market[:10]

    taken = set()
    seeds_available = seeds.get("MELON", 0) > 0
    farmer = _worker_action(farm, board_size, (fx, fy), seeds_available, taken, day)
    hands = [_worker_action(farm, board_size, hp, seeds_available, taken, day) for hp in hand_positions]

    return {"farmer": farmer, "hands": hands, "market": market}
