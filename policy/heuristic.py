"""Rule-based Kaggriculture agent.

v15: farmer + hired hands each patrol their own band of tiles in a snake
pattern; at each tile: harvest if ripe, water if thirsty, dig if spent/weed,
else plant that worker's assigned crop if seed is held. Sells are throttled
to 1 unit/turn rather than dumping the whole shed at once (SELL_THROTTLE).

THE biggest mechanical lever, found last and worth more than any parameter
sweep: harvest when yield is MAXIMIZED, not when it first becomes legal.
One-shot crops accrue +1 yield_units per WATER across the window
[(max_yield_day+1)//2, max_yield_day] (kaggriculture.py's WATER handler),
but HARVEST becomes legal at first_yield_day -- which for WHEAT is age 2
while its bonus window runs to age 4. The old "ripe = mature and
yield_units > 0" check therefore banked WHEAT at ~1-2 of its 6 possible
units, every single cycle. Gating ripe on (units >= max_yield or
age >= max_yield_day) was worth ~$33.1k -> ~$34.1k on its own (t~3.5), and
it also shifted the optimal crop mix: with WHEAT no longer harvested
half-grown it earns a second worker, and 4 MELON : 1 TOMATO : 2 WHEAT beat
the old 5:1:1 by another ~$2k. Combined: ~$33.1k -> ~$36.1k (+8.9%, t~13).

The same "read what the env actually rewards" idea again, on watering: a
plant only turns to weed at consecutive_unwatered >= 2, and watering only
ADDS yield inside a one-shot crop's bonus window. So watering a plant that
was watered yesterday, outside its window, buys nothing -- it just burns a
worker-turn. Skipping those waterings (water only when in the yield window,
or when consecutive_unwatered >= 1 and the plant would otherwise weed) was
worth ~$36.1k -> ~$36.7k (n=15, t~2.3). Re-swept the crop mix again after
it; 4:1:2 still wins (3:1:3 scores ~$32-33k).

Two end-of-season leaks, found by directly measuring what a full game
actually did rather than assuming the agent handles edges correctly:
(1) 25 of 111 plantings in one game could never mature before day 30
(~$1.4k wasted seed, plus every worker-turn spent tending them) --
_can_still_mature() now refuses to plant a crop that can't finish in time.
(2) 27 MELON were stranded in the shed at the final step -- SELL_PRICE_
FLOOR_FRAC's hold (lever 5) never releases before the season just ends, and
unsold shed inventory scores zero. The final LIQUIDATION_DAYS now ignore the
floor and raise the throttle to clear any backlog. Fixing (1) alone was a
large regression before a follow-up fix: workers whose primary crop can no
longer mature (~4 of 7, the MELON slice, after day 17) just sat idle
(PASS actions jumped to 2660) instead of switching to something that still
could -- added a WHEAT fallback (fastest cycle) for exactly that case, which
in turn needed WHEAT's seed buffer sized off the whole workforce instead of
just its own 2 primary growers, or most fallback plantings failed silently
for lack of seed (605 PLANT actions but only 112 HARVEST, first attempt).
Net effect small on mean money (~$36.3k -> ~$36.6k, n=15, not clearly
significant) but meaningfully reduces variance (stdev $729 -> $375) by
eliminating the worst-case stranded-inventory episodes.

Crop choice was the single biggest lever found: MELON ($250 base price, one
shot, max_yield=6) beats TOMATO ($60 base price, ongoing, max_yield=4) by
more than 3x in final money on its own, even though both crops cap out at a
similar few-units-per-tile yield -- MELON's per-unit price dominates.
Reaching that number required fixing a real correctness bug along the way:
a one-shot crop starts at yield_units=1 immediately on planting (see
kaggriculture.py's _new_plant), so the "ripe" check has to also gate on
age >= first_yield_day, or the agent wastes every turn on a HARVEST the env
silently no-ops until maturity instead of watering for the bonus-yield
window.

The second lever: MELON's harvests come in large lumps (one worker's whole
band matures together), and dumping 30-85 units in one SELL order walks
down the market's quadratic above-I0 price curve hard (~$226 avg realized
vs $250 base for an 85-unit dump, confirmed directly against
market_price()). Throttling every SELL to 1 unit/turn was strictly better
across every value swept (1/2/3/5/10/15/20/30).

The third lever: even throttled, all-MELON production (~168 units/season
from a full 25-tile quadrant) still saturates MELON's own market --
realized sell price tracked from ~$272 (early, scarcity premium) down to
~$51 (late, oversupply) over one game, confirmed by logging the observed
price at every SELL. Splitting workers across a second crop so production
doesn't all land in one market helped: 5:2 MELON:TOMATO was the peak of
every 2-crop split swept (6:1 through 3:4, not monotonic -- 6:1 actually
scored *below* pure MELON), ~$27.6k -> ~$31.3k.

The fourth and biggest-yet lever: WHEAT turned out to be a much better
*diversification partner* than TOMATO despite being a far worse crop on
its own (see "dropped" below) -- 5:2 MELON:WHEAT beat 5:2 MELON:TOMATO
(~$32.2k vs ~$31.3k), and a 3-way 5:1:1 MELON:TOMATO:WHEAT split beat both
2-crop mixes again (~$32.6k). Swept empirically: 6:1/4:3/3:4 MELON:WHEAT
ratios, MELON+CARROT+WHEAT, and MELON+TOMATO+CARROT 3-way mixes all scored
lower than 5:1:1 MELON:TOMATO:WHEAT. A crop's value as a diversification
slice is not the same question as its value as a sole crop -- WHEAT's fast,
low-value cycle apparently smooths cash flow / avoids saturating any one
market better than TOMATO's slower, higher-value one does, even though
TOMATO alone clearly beats WHEAT alone.

Hands are re-hired every day (the env wipes farm["hands"], the farmer's
position, carried inventories, and hire cost at end-of-day) so the agent
hires HANDS_CAP fresh hands each morning (hour 0) -- cheap, since the first
few hires of a day cost $1-3 each.

A fifth, smaller lever: hold inventory instead of selling when a crop's
price has crashed below SELL_PRICE_FLOOR_FRAC (0.4) of its base price,
unless the shed is close to capacity (in which case sell anyway -- losing
units to overflow discard is worse than a bad price). Swept 0.2/0.3/0.4/0.6:
0.4 was best, 0.6 held too aggressively and scored below the no-holding
baseline. ~$32.9k -> ~$33.1k -- real but modest, and only borderline
statistically distinguishable from the baseline at n=15 (t~1.4); kept
because it's directionally consistent across every threshold tested and
carries no downside (still fully sells through by game end).

The sixth lever, and the biggest since crop choice: land expansion,
finally profitable on the 7th attempt after six real, distinct failures
(v1: no extra labor, weeds; a fixed version with scaled hiring, still worse
than one quadrant under both TOMATO and MELON; attempt 5: a real
band-partitioning bug caused a total $0 wipeout; attempt 6, after fixing
that bug: market absorption is roughly fixed per product -- MARKET_I0 and
each crop's own T parameter don't scale with land -- so scaling the SAME
3-crop mix across 4 quadrants crashed MELON to the $1 price floor). What
finally worked was reading the market curve's own comment properly instead
of re-deriving the mix by feel: T is documented as "production capacity of
ONE 5x5 field" -- the env's economics assume a new quadrant grows a
DIFFERENT product, not more of an already-saturated one. Each extra
quadrant now gets its own primary crop (NE: STRAWBERRY, SW: CARROT, SE:
TOMATO, all avoiding MELON specifically) plus a WHEAT diversifier, mirroring
the shape that won at NW scale.

Getting there also meant discovering a second real constraint that had
nothing to do with land economics: hands are wiped and hire cost resets to
Fibonacci's start EVERY DAY, not once -- hiring N hands is a RECURRING daily
cost of sum(fib(0..N-1)). 10 hands/day is $143 cumulative; 21 hands/day is
$28,656. An initial design targeting a full 7-worker pool per extra
quadrant (28 workers total) was a genuine financial collapse (~$1.4-2.2k
final money) once `market[:10]`'s order-per-turn cap -- which had been
silently discarding most HIRE attempts and accidentally protecting the
economy -- was "fixed" to actually reach that target. Cut each extra
quadrant's pool to QUADRANT_WORKERS=3 (max 15 hands total, ~$376/day
cumulative) instead. Combined: ~$36.3k -> ~$41.9k (n=15, +15.5%, t~12).

A seventh discovery followed directly from that ~10-hand ceiling: NW's own
7 workers plus QUADRANT_WORKERS=3 for NE already consumes the entire
achievable workforce, so SW and SE -- if bought -- sat staffed with 0-1
workers (confirmed directly: NE always filled completely first, SW got 1
lone worker with no WHEAT diversifier, SE got zero). Buying them anyway
spent $2000+$4000 on land that was barely-to-never worked. `LAND_ORDER`
now stops at NE alone. ~$41.9k -> ~$47.0k (n=15, +12.1%, t~8.7).

An eighth followed from questioning an assumption carried over from NW
rather than re-tested: NE's crop mix copied NW's WHEAT-diversifier shape
without checking whether NE needed one. It doesn't -- the diversifier
exists to stop a single crop saturating its OWN market (real at NW's
7-worker scale), but NE only ever gets ~3 workers, too small a production
volume to saturate STRAWBERRY's market on its own. Went all-STRAWBERRY,
no WHEAT: ~$47.0k -> ~$51.3k (n=15, +9.2%, t~6.8).

Things tried and dropped, documented so they don't get re-litigated without
new evidence:
- Fertilizer, twice. First pass (all crops): bonus is capped by the same
  `min(max_yield, ...)` as ordinary production -- reaches the cap faster,
  never raises it, for MELON and TOMATO specifically (checked the actual
  arithmetic: MELON's 7-day window already exceeds its cap via plain
  watering alone, 1+7*1=8 capped at 6; TOMATO's 4 ticks x 1 already equal
  its cap of 4). But WHEAT's window is only 3 days -- 1+3*1=4, under its
  cap of 6 -- so fertilizer's +2/water genuinely raises realized yield
  there (1+3*2=7, capped at 6: a real +50%/cycle, not just faster-to-the-
  same-place). Built it properly for WHEAT only: BUY_PRODUCT, a worker
  picks it up (fixed two more real bugs along the way -- PICKUP only
  recognized one of the four valid shed tiles, and hands don't exist in
  the observation until hour 1 since they're hired *during* hour 0's
  action, so a hour==0 pickup gate silently never fired for any hand,
  which is every WHEAT worker in this mix). Once actually working
  end-to-end (confirmed via action counts: 54 pickups, 65 applications),
  it still scored net-negative (~$30-30.5k vs ~$36.6k) -- the logistics
  (pickup trips, and the *daily* pickup delaying every WHEAT worker's
  first move of the day) cost more than the yield gain is worth, even
  where the yield math is genuinely favorable. Fertilizer is now closed
  off for every crop in this mix, for two different, both-confirmed
  reasons depending on the crop.
- Animal ranching (SHEEP). Unlike crops, animals have no lifetime yield cap
  in kaggriculture.py's _daily_refresh_animals, and pending_care_bonus
  accumulates uncapped within an inter-tick gap (reset only when actually
  consumed on a fed tick day) -- traced the exact logic and confirmed a
  real steady-state 3x multiplier for SHEEP (interval=3) with full daily
  CARE+FEED: 1(base)+2(bonus)=3 units/tick vs 1 without. Built a dedicated
  "rancher" worker (replacing one MELON slot): BUILD_PASTURE, BUY_ANIMAL,
  PICKUP/PLACE, daily FEED+CARE, HARVEST+SELL WOOL, with WHEAT feed stock
  protected from the generic auto-sell loop (same bug shape as the
  FERTILIZER-reselling one) and PICKUP recognizing all four shed tiles.
  Confirmed working end-to-end (~33 WOOL sold/game, ~$180 avg realized
  price, pending_care_bonus sitting at the expected 2-3 steady-state) --
  but still scored modestly below the single-quadrant baseline (~$34.7k vs
  ~$36.3k). Tried having the rancher farm WHEAT on its band's other tiles
  during ranch downtime to recover the idle-tile cost -- barely changed
  anything, meaning there's little true idle time once shed trips, feed,
  and care are accounted for.

  Tested the flagged follow-up too: 2 SHEEP per rancher, to see if a
  second animal amortizes the fixed daily cost (shed trip, two stationary
  actions) across more WOOL revenue. Built and confirmed working (2x
  BUILD_PASTURE/PLACE, ~52 FEED/51 CARE, both animals reaching full
  steady-state care) -- but it came out *worse* than the single-animal
  version, not better (~$34.2k mean, n=15), and with far higher variance
  (stdev $3.7k vs $375 for v12) -- a real reliability regression, not just
  a wash. The fixed-cost-amortization hypothesis doesn't hold: scaling up
  concentrates more of the farm's cash and labor into a single higher-
  variance venture rather than smoothing anything out. Both animal counts
  now closed on real evidence -- 1 is a near miss, 2 is worse and
  riskier -- rather than left as an assumed-favorable unknown.
- WHEAT instead of MELON: much faster cycle (first_yield_day=2 vs 10) but
  25x lower base price ($25 vs $250) isn't compensated by the extra cycles.
- STRAWBERRY instead of MELON: scored ~$20.5-22.2k, well below MELON, and
  adding it as a third crop to the MELON:TOMATO mix (4:2:1 or 5:1:1) also
  underperformed the clean 2-crop 5:2 split (WHEAT, tried later, didn't).
- Reducing HANDS_CAP during MELON's pre-harvest dry spell (labor looked
  idle, so tried hiring fewer hands days 0-7): scored lower, not higher --
  those early hands are doing essential planting/watering setup for tiles
  that mature later, not sitting idle.
- Re-swept HANDS_CAP (4/5/6/8) and SELL_THROTTLE (2/3/5) under the v7
  crop-mix specifically, in case the optimal values shifted once production
  split across markets -- both confirmed unchanged from the pure-MELON
  tuning.
- Nearby 3-crop ratios (4:1:2, 4:2:1 MELON:TOMATO:WHEAT) and a 4-crop
  spread (4 MELON:1 each TOMATO/WHEAT/CARROT) all scored below 5:1:1 --
  sacrificing a 2nd MELON worker for broader diversification isn't worth
  it; one worker's worth of diversification is the right amount. (This was
  about NW alone, before land expansion finally worked -- see above.)
"""

# Split workers across three crops (4 MELON : 1 TOMATO : 2 WHEAT) so
# production doesn't all land in one market and crash its own price -- see
# docstring. Swept empirically, not derived: ratios and crop choice both
# matter and aren't monotonic or predictable from each crop's solo value.
# Re-swept after the harvest-timing fix (5:1:1, 4:1:2, 5:0:2, 6:0:1, 3:1:3,
# 4:2:1): the optimum moved from 5:1:1 to 4:1:2, because WHEAT is no longer
# harvested half-grown and so earns a second worker. 3:1:3 overshoots.
CROP_MIX = ["MELON"] * 4 + ["TOMATO"] * 1 + ["WHEAT"] * 2
HANDS_CAP = 6  # hands hired per day -> up to 7 total workers (farmer + hands).
# Swept 2/4/6/8 for MELON: results were close (~26.3-27.1k) and not
# monotonic -- MELON's economics (labor mostly idles during the 10-12 day
# pre-harvest dry spell, then a couple of huge lump-sum harvests) make labor
# count matter far less than for TOMATO. 6 scored best of those tested, and
# re-confirmed best again after the crop-mix change (see docstring).
SEED_BUFFER_PER_WORKER = 1  # re-swept (1/2/3) under the v7 crop-mix: 1 wins
# -- keeping less seed capital tied up per crop outweighs the restock
# frequency, now that 3 crops each need their own buffer.
SELL_THROTTLE = 1  # cap units sold per turn -- large one-shot dumps (a
# harvest wave of 30-85 MELON at once, confirmed empirically) walk down the
# quadratic above-I0 price curve hard (avg realized price ~$226 vs $250 base
# for an 85-unit dump). Swept 1/2/3/5/10/15/20/30: strictly monotonic, lower
# always wins -- selling 1/turn (every turn, so still a full sell-through by
# game end: confirmed 0 units stranded in the shed at the final step) lets
# the market's slow daily consumption (-1 unit/day for MELON) recover
# between each unit instead of quoting many units against the same dump.
SELL_PRICE_FLOOR_FRAC = 0.4
# price has crashed below this fraction of base -- unless shed is close to
# capacity, in which case sell anyway (losing units to overflow discard is
# worse than a bad price).
SHED_CAPACITY = 100
BASE_PRICE = {"TOMATO": 60, "MELON": 250, "CARROT": 35, "WHEAT": 25, "STRAWBERRY": 120}
# Only banked money scores -- product still sitting in the shed at the final
# step is worth nothing. Measured 27 MELON stranded that way (the price-floor
# hold above never released before the season ended), so the last few days
# ignore the floor and clear the backlog at any price.
SEASON_DAYS = 30  # env default (episodeSteps 720 / turnsPerDay 24)
LIQUIDATION_DAYS = 3  # force-sell during the final N days
LIQUIDATION_THROTTLE = 6  # and lift the 1/turn cap so the backlog clears

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
    "CARROT": {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "WHEAT": {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
}

# Land expansion, redesigned around a real insight instead of re-scaling
# the same 3-crop mix (which measurably crashed MELON to the $1 price floor
# when tried before): the market's own T parameter is documented in
# kaggriculture.py as "production capacity of ONE 5x5 field over a 24-day
# window" -- the env's economics assume a new quadrant grows a DIFFERENT
# product, not more of the same one. Each extra quadrant gets its own
# primary crop (chosen to avoid MELON, the one market we already know
# saturates hard) plus the same WHEAT-diversifier shape that won at NW
# scale, and its own worker pool capped like NW's.
NW_WORKERS = 7  # NW's band stays fixed at this size regardless of land --
# see the land-expansion docstring entries: diluting an established
# worker's tile density the instant land unlocks caused a total wipeout
# once already, independent of this specific crop-mix redesign.
QUADRANT_WORKERS = 3  # each EXTRA quadrant's own fixed worker pool -- much
# smaller than NW's 7. Hands are wiped and hire cost resets to Fibonacci's
# start EVERY DAY (not a one-time cost), so hiring N hands is a RECURRING
# daily cost of sum(fib(0..N-1)): 10 hands/day is $143 cumulative, but 21
# hands/day is $28,656 -- discovered the hard way when an earlier version
# targeted 7 workers x 3 extra quadrants (28 total) and it was a real
# financial collapse (final money $1.4-2.2k vs the ~$36k baseline), not a
# land-economics problem. 3 workers/quadrant keeps total hands (up to
# HANDS_CAP + QUADRANT_WORKERS*3 = 15) in the affordable range.
# NE is all-STRAWBERRY, no WHEAT diversifier -- unlike NW, tested and
# confirmed better without one (~$47.0k -> ~$51.3k, n=15, t~6.8). The
# WHEAT-diversifier lever exists to stop a single crop's OWN market from
# saturating; at NW's 7-worker scale that's real (an all-MELON quadrant
# measurably crashed MELON's price). NE only ever gets ~3 workers (the
# ~10-hand ceiling, see HIRE comment below), a small enough production
# volume that STRAWBERRY's own market (T=100) doesn't saturate -- so the
# diversifier was pure dilution into a lower-value crop for no benefit.
# SW/SE keep a diversifier since they're currently unbought (LAND_ORDER
# stops at NE) and untested at this scale -- left as documented
# placeholders, not verified either way.
QUADRANT_CROP_MIX = {
    "NE": ["STRAWBERRY", "STRAWBERRY", "STRAWBERRY"],
    "SW": ["CARROT", "CARROT", "WHEAT"],
    "SE": ["TOMATO", "TOMATO", "WHEAT"],
}
# LAND_ORDER only lists NE: the ~10-hand ceiling (see the HIRE comment in
# agent()) means NW(7)+NE(QUADRANT_WORKERS=3) already consumes the whole
# achievable workforce -- SW and SE, if bought, sat staffed with 0-1
# workers (confirmed directly: at 11 total workers, NE always filled
# completely first, SW got 1 lone worker with no WHEAT diversifier, SE got
# zero). Buying them anyway spent $2000+$4000 on land that was barely-to-
# never worked. Stopping at NE alone (saving that $6000 and never diluting
# the achievable workforce across unworkable land) was worth ~$41.9k ->
# ~$47.0k (n=15, +12.1%, t~8.7) -- almost as large a jump as buying land at
# all was in the first place.
# SW/SE's crop-mix entries and price are kept below in case a future
# change (e.g. a higher achievable hand count) makes them viable again.
LAND_ORDER = ["NE"]
LAND_PRICES = {"NE": 1000, "SW": 2000, "SE": 4000}
STARTING_MONEY = 3000
CASH_RESERVE = 200
LAND_MIN_DAY = 3


def _snake_positions(size):
    for y in range(size):
        row = range(size) if y % 2 == 0 else range(size - 1, -1, -1)
        for x in row:
            yield x, y


def _workable_positions(tiles):
    size = len(tiles)
    return [(x, y) for x, y in _snake_positions(size) if tiles[y][x] != "LOCKED"]


def _quadrant_of(x, y, size):
    half = size // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def _positions_in_quadrant(tiles, quadrant):
    size = len(tiles)
    return [
        (x, y) for x, y in _snake_positions(size)
        if tiles[y][x] != "LOCKED" and _quadrant_of(x, y, size) == quadrant
    ]


def _shed_tiles(size):
    """The four inner-corner tiles PICKUP/DROP work from. Farmer and hands
    spawn on one of these each morning (kaggriculture.py's _default_spawn /
    _spawn_hand), so any of the four counts, not just one fixed corner."""
    half = size // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]


def _band_for_worker(positions, worker_idx, num_workers):
    if not positions:
        return []
    chunk = max(1, len(positions) // num_workers)
    start = worker_idx * chunk
    end = len(positions) if worker_idx == num_workers - 1 else start + chunk
    return positions[start:end]


def _crop_exhaust_age(crop_info):
    return crop_info["first_yield_day"] + (crop_info["max_yield"] - 1) * max(1, crop_info["interval"])


def _can_still_mature(crop_info, day):
    """Would a seed planted today reach a harvest before the season ends?

    Planting one that can't is pure loss: the seed cost, plus every
    worker-turn spent planting and watering a crop nobody will ever harvest.
    Measured 25 such plantings (~$1.4k of seed) in a single game before this
    check existed. One-shot crops are harvested at max_yield_day (we wait for
    full yield); ongoing crops start paying at first_yield_day.
    """
    days_needed = (
        crop_info["max_yield_day"] if not crop_info["ongoing"] else crop_info["first_yield_day"]
    )
    return day + days_needed <= SEASON_DAYS - 1


def _next_target_in_band(tiles, band, px, py, day, crop_info):
    if not band:
        return px, py, "none"
    start = band.index((px, py)) if (px, py) in band else 0
    ordered = band[start:] + band[:start]
    exhaust_age = _crop_exhaust_age(crop_info)
    for x, y in ordered:
        t = tiles[y][x]
        if t is None:
            return x, y, "empty"
        if isinstance(t, dict) and t.get("kind") == "WEED":
            return x, y, "weed"
        if isinstance(t, dict) and t.get("kind") == "PLANT":
            age = day - t.get("planted_day", day)
            units = t.get("yield_units", 0)
            if crop_info["ongoing"]:
                ripe = units > 0
            else:
                # One-shot crops keep accruing +1 yield per WATER until
                # max_yield_day (see kaggriculture.py's WATER handler), so
                # harvesting the moment it's legal (first_yield_day) banks a
                # partly-grown crop -- WHEAT at age 2 has ~1-2 of its 6 units.
                # Wait for the yield cap or the last bonus day, whichever
                # comes first.
                ripe = (
                    age >= crop_info["first_yield_day"]
                    and units > 0
                    and (units >= crop_info["max_yield"] or age >= crop_info["max_yield_day"])
                )
            if ripe:
                return x, y, "ripe"
            if not t.get("watered_today", False):
                # Watering is only worth a turn if it either buys yield or
                # prevents a weed. It adds yield only inside a one-shot
                # crop's bonus window; and a plant only turns to weed at
                # consecutive_unwatered >= 2, so one watered in the last
                # day (== 0) can safely skip today.
                in_yield_window = (
                    not crop_info["ongoing"]
                    and (crop_info["max_yield_day"] + 1) // 2 <= age <= crop_info["max_yield_day"]
                )
                must_water = t.get("consecutive_unwatered", 1) >= 1
                if in_yield_window or must_water:
                    return x, y, "thirsty"
            if crop_info["ongoing"] and age >= exhaust_age:
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


def _worker_action(tiles, band, pos, seeds_available, day, crop, crop_info, fallback_seeds_available):
    px, py = pos
    tx, ty, state = _next_target_in_band(tiles, band, px, py, day, crop_info)
    if (px, py) == (tx, ty):
        if state == "ripe":
            return ["HARVEST"]
        if state == "thirsty":
            return ["WATER"]
        if state in ("spent", "weed"):
            return ["DIG"]
        if state == "empty":
            if seeds_available and _can_still_mature(crop_info, day):
                return ["PLANT", crop]
            # This worker's assigned crop can no longer mature before the
            # season ends -- fall back to WHEAT (fastest cycle) rather than
            # sitting idle for what can be a third of the season. Measured
            # PASS actions jump from ~2000 to ~2660 without this fallback,
            # since ~4 of 7 workers (the MELON slice) stop having anything
            # to plant after day 17.
            if crop != "WHEAT" and fallback_seeds_available and _can_still_mature(CROP_INFO["WHEAT"], day):
                return ["PLANT", "WHEAT"]
        return ["PASS"]
    move = _step_toward(px, py, tx, ty)
    return [move] if move else ["PASS"]


def _worker_quadrant_and_crop(i, extra_unlocked):
    """Worker index -> (quadrant, crop, local_idx_within_that_quadrant).
    NW's first NW_WORKERS slots use CROP_MIX exactly as in the
    single-quadrant version; every quadrant beyond that gets its own fixed
    QUADRANT_WORKERS-sized pool from QUADRANT_CROP_MIX, filled in unlock
    order. Returns (None, None, None) if there's no assigned quadrant yet
    (more workers hired than currently-unlocked land can support --
    band-staging handles that gracefully, see NW_WORKERS docstring)."""
    if i < NW_WORKERS:
        return "NW", CROP_MIX[i % len(CROP_MIX)], i
    j = i - NW_WORKERS
    q_idx = j // QUADRANT_WORKERS
    if q_idx >= len(extra_unlocked):
        return None, None, None
    quadrant = extra_unlocked[q_idx]
    local_idx = j % QUADRANT_WORKERS
    mix = QUADRANT_CROP_MIX[quadrant]
    return quadrant, mix[local_idx % len(mix)], local_idx


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
    day = obs.get("day", 0)
    hires_today = farm.get("hires_today", 0)
    seeds = private.get("seeds", {})
    shed = private.get("shed", {})
    hand_positions = [tuple(p) for p in farm.get("hands", [])]
    num_workers = 1 + len(hand_positions)
    unlocked = set(farm.get("unlocked_quadrants", ["NW"]))
    extra_unlocked = [q for q in LAND_ORDER if q in unlocked]
    n_unlocked_extra = len(extra_unlocked)

    market = []

    # Buy the next land quadrant only once real farming profit -- not the
    # opening bankroll -- comfortably covers it, and only after a few days.
    if n_unlocked_extra < len(LAND_ORDER) and day >= LAND_MIN_DAY:
        next_quad = LAND_ORDER[n_unlocked_extra]
        cost = LAND_PRICES[next_quad]
        if money - STARTING_MONEY >= cost * 2 and money - cost >= CASH_RESERVE:
            market.append(["BUY_LAND"])

    # Re-hire the day's hands -- cheap (first few hires cost $1-3) since the
    # env wipes hands and hire cost at EOD. hands_cap can call for 15 with
    # land unlocked, but only ~10 ever actually land: maxMarketOrdersPerTurn
    # caps hour 0's whole market list (BUY_LAND + HIRE*N) at 10 total, so
    # anything past the 10th HIRE entry is silently discarded -- confirmed
    # via actual hand counts (10, not 15, from mid-game on). That turns out
    # to be a feature, not a bug worth fixing: hire cost resets and
    # recompounds EVERY day (see the land-expansion docstring entry), so
    # this cap keeps the daily hire bill in the cheap end of that curve
    # (~10 hands is $143/day) instead of the expensive one. Tried lifting it
    # (spread hiring across multiple turns to actually reach 15+) and it was
    # a regression -- on days the fuller target still wasn't reached, HIRE
    # kept competing with SELL/BUY_SEED for market slots all day instead of
    # just the first turn, starving normal operations of cash.
    hands_cap = HANDS_CAP + QUADRANT_WORKERS * n_unlocked_extra
    if hour == 0:
        n = hires_today
        budget = max(0.0, money - CASH_RESERVE) * 0.5
        spent = 0
        hired = 0
        while hired < hands_cap:
            cost = _fib(n)
            if spent + cost > budget:
                break
            spent += cost
            n += 1
            hired += 1
        market.extend([["HIRE"]] * hired)

    market_prices = (obs.get("market", {}) or {}).get("prices", {})
    liquidating = day >= SEASON_DAYS - LIQUIDATION_DAYS
    throttle = LIQUIDATION_THROTTLE if liquidating else SELL_THROTTLE
    for item, qty in shed.items():
        if qty <= 0:
            continue
        base = BASE_PRICE.get(item)
        price = market_prices.get(item)
        near_full = qty >= SHED_CAPACITY - 5
        holding_ok = not near_full and not liquidating
        if base and price is not None and price < base * SELL_PRICE_FLOOR_FRAC and holding_ok:
            continue  # hold -- price has crashed, wait for it to recover
        market.append(["SELL", item, min(qty, throttle)])

    worker_info = [_worker_quadrant_and_crop(i, extra_unlocked) for i in range(num_workers)]
    worker_crops = [c for (_, c, _) in worker_info]
    crops_in_use = {c for c in worker_crops if c is not None}
    for crop in crops_in_use:
        crop_info = CROP_INFO[crop]
        workers_on_crop = worker_crops.count(crop)
        # WHEAT also absorbs every other worker's fallback plantings once
        # their own crop can no longer mature (see _worker_action) -- size
        # its buffer off the full workforce, not just its own primary
        # assignment, or most fallback PLANT attempts fail silently for
        # lack of seed (measured: 605 PLANT actions but only 112 HARVEST
        # with an undersized buffer here).
        target_workers = num_workers if crop == "WHEAT" else workers_on_crop
        seed_target = max(1, target_workers) * SEED_BUFFER_PER_WORKER
        have = seeds.get(crop, 0)
        if have < seed_target and money >= crop_info["seed"]:
            market.append(["BUY_SEED", crop, seed_target - have])

    market = market[:10]

    wheat_seeds_available = seeds.get("WHEAT", 0) > 0
    quadrant_positions = {}  # cache: quadrant -> its workable tile list

    def dispatch(i, pos):
        quadrant, crop, local_idx = worker_info[i]
        if quadrant is None:
            return ["PASS"]  # more workers hired than land currently supports
        if quadrant not in quadrant_positions:
            quadrant_positions[quadrant] = _positions_in_quadrant(tiles, quadrant)
        pool_size = NW_WORKERS if quadrant == "NW" else QUADRANT_WORKERS
        band = _band_for_worker(quadrant_positions[quadrant], local_idx, pool_size)
        seeds_available = seeds.get(crop, 0) > 0
        return _worker_action(
            tiles, band, pos, seeds_available, day, crop,
            CROP_INFO[crop], wheat_seeds_available,
        )

    farmer_action = dispatch(0, (fx, fy))
    hands_actions = [dispatch(i, hp) for i, hp in enumerate(hand_positions, start=1)]

    return {"farmer": farmer_action, "hands": hands_actions, "market": market}
