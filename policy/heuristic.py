"""Rule-based Kaggriculture agent.

Strategy: scan the farmer across every unlocked tile in a snake pattern.
At each tile: harvest if ripe, water if thirsty, else plant the target crop
if we're holding seed. Sell the shed's contents and restock seed every turn;
once money clears a threshold, buy the next land quadrant.

TOMATO is the default target crop: moderate seed cost (50), ongoing yield
(produces repeatedly once mature) beats a one-shot crop like the "starter"
baseline's CARROT loop once a few tiles are in rotation.
"""

TARGET_CROP = "TOMATO"
SEED_RESTOCK = 5
# Land/hands are deliberately NOT bought yet: expanding the patrol area
# without more hands to work it means more tiles go unwatered -> weeds ->
# wasted seed money, which measurably lost more than it earned (see README).


def _snake_positions(size):
    for y in range(size):
        row = range(size) if y % 2 == 0 else range(size - 1, -1, -1)
        for x in row:
            yield x, y


def _next_target_tile(tiles, fx, fy):
    size = len(tiles)
    positions = list(_snake_positions(size))
    start = positions.index((fx, fy)) if (fx, fy) in positions else 0
    ordered = positions[start:] + positions[:start]
    for x, y in ordered:
        t = tiles[y][x]
        if t == "LOCKED":
            continue
        if t is None:
            return x, y, "empty"
        if isinstance(t, dict) and t.get("kind") == "PLANT":
            if t.get("yield_units", 0) > 0:
                return x, y, "ripe"
            if not t.get("watered_today", False):
                return x, y, "thirsty"
    return fx, fy, "none"


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
    seeds = private.get("seeds", {})
    shed = private.get("shed", {})

    market = []
    for item, qty in shed.items():
        if qty > 0:
            market.append(["SELL", item, qty])

    if seeds.get(TARGET_CROP, 0) == 0 and money >= 50:
        market.append(["BUY_SEED", TARGET_CROP, SEED_RESTOCK])

    market = market[:10]

    tx, ty, state = _next_target_tile(tiles, fx, fy)
    if (fx, fy) == (tx, ty):
        if state == "ripe":
            farmer = ["HARVEST"]
        elif state == "thirsty":
            farmer = ["WATER"]
        elif state == "empty" and seeds.get(TARGET_CROP, 0) > 0:
            farmer = ["PLANT", TARGET_CROP]
        else:
            farmer = ["PASS"]
    else:
        move = _step_toward(fx, fy, tx, ty)
        farmer = [move] if move else ["PASS"]

    hands = [["PASS"] for _ in farm.get("hands", [])]
    return {"farmer": farmer, "hands": hands, "market": market}
