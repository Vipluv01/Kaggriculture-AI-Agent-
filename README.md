# kaggriculture

Agent for Kaggle's [Kaggriculture](https://www.kaggle.com/competitions/kaggriculture) simulation
competition — two players each run a farm (crops, animals, hired labor) and trade on a shared
dynamic-price market over a 720-turn (30-day) season. Score is money in the bank at the end.

## Setup

```bash
uv venv .venv
uv pip install --python .venv/bin/python -U kaggle-environments kaggle
```

## Local dev loop

```bash
.venv/bin/python scripts/evaluate.py            # heuristic agent vs baselines, N episodes
.venv/bin/python -c "
from kaggle_environments import make
env = make('kaggriculture', configuration={'episodeSteps': 720}, debug=True)
env.run(['main.py', 'starter'])
env.render(mode='html')
" > replay.html                                   # visual replay
```

## Submission

Requires a Kaggle API token (`~/.kaggle/access_token`) and having joined the competition
(accept rules on the competition page) first. Bundle `main.py` with `policy/` since the
entrypoint imports from it:

```bash
tar -czf submission.tar.gz main.py policy/
.venv/bin/kaggle competitions submit kaggriculture -f submission.tar.gz -m "message"
.venv/bin/kaggle competitions submissions kaggriculture   # check status/score
```

## Status

v16 heuristic (`policy/heuristic.py`) — current best, submitted. Progression:

| version | change | mean $ (10+ episodes/opponent) |
|---|---|---|
| v1 | single farmer, single quadrant, TOMATO | ~4.6-4.8k |
| v2 | +4 hired hands/day, band-patrol | ~5.8-6.2k |
| v3 | +dig & replant spent tiles | ~7.7-9.8k |
| v4 | crop swap: MELON instead of TOMATO + HANDS_CAP retuned to 6 | ~27.1k |
| v5 | +throttle SELL to 1 unit/turn instead of dumping the shed | ~27.6k |
| v6 | +CROP_MIX: split workers 5 MELON : 2 TOMATO | ~31.3k |
| v7 | +3-way CROP_MIX: 5 MELON : 1 TOMATO : 1 WHEAT | ~32.5k |
| v8 | +SEED_BUFFER_PER_WORKER retuned 2→1 for the 3-crop mix | ~32.9k |
| v9 | +hold inventory below 40% of base price instead of always selling | ~33.1k |
| v10 | harvest at max yield, not first legal moment + retuned mix 4:1:2 | ~36.1k |
| v11 | +skip watering that buys nothing outside the bonus window | ~36.7k |
| v12 | +refuse to plant crops that can't mature + season-end liquidation | ~36.3-36.6k |
| v13 | **land expansion, working**: each extra quadrant grows a different crop | ~41.9k |
| v14 | stop buying land nobody can staff: only NE, not all 3 extra quadrants | ~47.0k |
| v15 | **drop NE's WHEAT diversifier**: not needed at NE's small (~3-worker) scale | ~51.3k |
| v16 | nearest-actionable-tile targeting instead of fixed snake-order traversal | **~51.5k** |

Real ladder scores (all `COMPLETE`; scores are a live skill rating against a growing ~7000-team
opponent pool, not raw dollars, and drift over time for everyone as that pool strengthens —
same-window comparisons are what's meaningful, not the absolute number): v1=267.1, v2=263.3,
v3=201.2, v4 climbed 372.7→441.4→439.7→426.6 across re-submits while it was being tuned,
v5=361.6, v6=445.9, v7=398.9, v8=426.6, v9=440.2, v10=473.1, v11=406.7, v12=416.5, v13=489.2,
v14=466.8, v15=499.4, **v16=pending submission**.

### Levers found

Each verified independently (usually an n=10-15 episode check, `t`-statistic where the effect
was close) before being kept.

1. **Crop choice.** MELON ($250 base, one-shot, max_yield=6) beats TOMATO ($60 base, ongoing,
   max_yield=4) by 3x+ alone, even though both cap out at a similar few-units-per-tile yield.
   Needed a real bug fix along the way: a one-shot crop's tile starts at `yield_units=1`
   immediately on planting (`_new_plant`), so a naive "yield_units > 0 means ripe" check fires
   HARVEST from turn one — the env silently no-ops that until `first_yield_day`, wasting turns
   that should've been spent watering for the bonus-yield window. Ripe now also gates on
   `age >= first_yield_day` for non-ongoing crops.
2. **Sell throttling.** MELON harvests land in large lumps (a worker's whole band matures
   together); dumping 30-85 units in one SELL order walks down the market's quadratic
   above-I0 price curve hard (an 85-unit dump nets ~$226 avg vs the $250 base, confirmed
   directly against `market_price()`). Throttling every SELL to 1 unit/turn was strictly
   better across every value swept (1/2/3/5/10/15/20/30) and still fully sells through by
   game end.
3. **Crop mix.** Even throttled, an all-MELON quadrant (~168 units/season) saturates MELON's
   own market on its own — logging the observed price at every sell showed it walking from
   ~$272 (early, scarcity premium) down to ~$51 (late, oversupply) over the course of one
   game. Splitting workers across MELON and TOMATO so production doesn't all land in one
   market pushed mean money from ~$27.6k to ~$31.3k. The ratio was swept empirically (not
   derivable analytically): 6:1 through 3:4, plus two 3-crop mixes adding STRAWBERRY. 5:2
   MELON:TOMATO was a clear, non-monotonic peak — 6:1 actually scored *below* pure MELON.
4. **The right diversification partner isn't the best solo crop (the biggest lever of all up
   to this point).** WHEAT alone is a weak crop (25x lower base price than MELON, only
   compensated by a much faster cycle) — yet swapping it in as the *diversification* slice
   instead of TOMATO beat TOMATO's own mix (5:2 MELON:WHEAT ~$32.2k vs 5:2 MELON:TOMATO
   ~$31.3k), and a 3-way 5:1:1 MELON:TOMATO:WHEAT split beat both 2-crop mixes again
   (~$32.5k, then ~$32.9k after retuning `SEED_BUFFER_PER_WORKER` down to 1 for the new mix).
   Nearby ratios (4:1:2, 4:2:1) and a 4-crop spread (adding CARROT) all scored lower — one
   worker's worth of diversification, split across exactly two secondary crops, is the sweet
   spot found so far.

   (Levers 1-4 all trace back to the competition's own official tutorial notebook,
   `bovard/kaggriculture-getting-started`, pulled via `kaggle kernels pull`. It builds a naive
   single-crop "Melon Maxxer" and calls out its exact weaknesses: no hired hands/land,
   single-crop-only, no fertilizer, and dumping the whole shed in one sell. All four are now
   addressed here.)

5. **Harvest at max yield, not first legal moment (v10, biggest lever since crop choice).**
   One-shot crops accrue `+1 yield_units` per `WATER` across a bonus window
   `[(max_yield_day+1)//2, max_yield_day]`, but `HARVEST` becomes legal at `first_yield_day` —
   for WHEAT that's age 2 while the bonus window runs to age 4. The old "ripe" check banked
   WHEAT at ~1-2 of its 6 possible units every cycle. Gating ripe on
   `yield_units >= max_yield OR age >= max_yield_day` was worth ~$33.1k → ~$34.1k alone, and
   shifted the optimal mix from 5:1:1 to 4:1:2 MELON:TOMATO:WHEAT (WHEAT now earns a second
   worker since it's no longer harvested half-grown). Combined: ~$33.1k → ~$36.1k (+8.9%).
6. **Skip watering that buys nothing (v11).** A plant only weeds at `consecutive_unwatered >=
   2`, and watering only adds yield inside the bonus window — so watering a plant that was
   already watered yesterday, outside that window, burns a worker-turn for nothing.
   ~$36.1k → ~$36.7k.
7. **Land expansion, working (v13) — the biggest lever yet, after six real, distinct
   failures.** v1: no extra labor for the new quadrant, it just grew weeds and lost money
   net. A fixed version with scaled hiring was still worse than staying at one quadrant,
   under both TOMATO and MELON. Attempt 5 had a real band-partitioning bug that caused a
   total $0 wipeout — unlocking a quadrant instantly diluted an already-established worker's
   tile density before hiring could catch up. Attempt 6, after fixing that bug, was *still*
   far worse, because market absorption is roughly fixed per product (`MARKET_I0`, each
   crop's own `T`) regardless of how much land you own — scaling the same 3-crop mix across
   4 quadrants crashed MELON straight to the **$1 price floor**. What finally worked: reading
   the market curve's own comment properly instead of re-deriving the mix by feel — `T` is
   documented as "production capacity of ONE 5x5 field," meaning a new quadrant is meant to
   grow a *different* product, not more of an already-saturated one. Each extra quadrant now
   gets its own primary crop (NE: STRAWBERRY, avoiding MELON specifically). Getting there
   also meant discovering hands are wiped and hire cost resets to Fibonacci's start *every
   day* (not once) — hiring 21 hands/day is $28,656 cumulative, not a typo.
   `maxMarketOrdersPerTurn`'s per-turn cap of 10 had been silently discarding most hire
   attempts and accidentally protecting the economy; "fixing" that to actually reach a
   28-worker target was a real financial collapse (~$1.4-2.2k). Settled on a small worker
   pool per extra quadrant instead. Combined: ~$36.3k → ~$41.9k (n=15, +15.5%, t≈12).
8. **Stop buying land nobody can staff (v14).** Following directly from the Fibonacci
   discovery above: NW's 7 workers already consume most of the achievable hand budget, so
   SW and SE, once bought, sat staffed with 0-1 workers — confirmed directly by inspecting
   the actual worker→quadrant assignment at day 25. Buying them anyway spent $2000+$4000 on
   land that was barely-to-never worked. `LAND_ORDER` now stops at NE alone. Re-tried
   assigning the strongest solo crops (TOMATO, then CARROT) to the always-staffed NE slot
   instead of STRAWBERRY — both worse: TOMATO overlaps with NW's own TOMATO worker,
   re-triggering the exact market-saturation problem land diversification was built to
   avoid, and CARROT's larger market headroom (`T`=450) still loses to STRAWBERRY's higher
   base price ($120 vs $35) at this small a production scale. ~$41.9k → ~$47.0k (n=15,
   +12.1%, t≈8.7).
9. **Drop NE's WHEAT diversifier (v15).** NE's crop mix copied NW's WHEAT-diversifier shape
   without re-testing whether NE actually needed one. It doesn't: the diversifier exists to
   stop a single crop saturating its *own* market, which is real at NW's 7-worker scale (an
   all-MELON quadrant measurably crashed MELON's price) but NE only ever gets ~3 workers —
   too small a production volume to saturate STRAWBERRY's market (`T`=100) on its own. Went
   all-STRAWBERRY: ~$47.0k → ~$51.3k (n=15, +9.2%, t≈6.8). Also re-tested the land-purchase
   gating (removing the 2x-profit-margin safety check entirely was a regression — buys land
   turn 1, draining the capital NW's own dry spell needs; milder 1.0-3.0x multipliers were
   all within noise of the current 2x) and `HANDS_CAP` (5 and 7 both worse than 6) — both
   confirmed already well-tuned.
10. **Re-verified the ~10-hand ceiling is stale, and re-swept around it (v15, no code
    change).** The v13/v14 comments described the market-order cap
    (`maxMarketOrdersPerTurn`=10) as actively truncating HIRE down from a higher target —
    true when the hire target was 15, but stale now: v15's leaner all-STRAWBERRY NE config
    puts the target at 9 (`HANDS_CAP`=6 + `QUADRANT_WORKERS`=3), which fits under the cap on
    its own. Confirmed directly by instrumenting the pre-truncation market-list length across
    a full game: the cap only bites on ~1-1.5% of turns (always hour 0, when SELL also
    queues 2-3 items), not every day as the old comment implied. Re-swept
    `QUADRANT_WORKERS` (4, 5) under this leaner config on the theory that the ceiling
    reasoning might have changed the optimum — it hasn't: 4 is statistically flat against 3
    (n=15: $50,927 vs $50,528, a $399 gap against a ~$700 standard error) and 5 is clearly
    worse (~$46-47k). `QUADRANT_WORKERS=3` stays. Also tried reprioritizing the rare hour-0
    overflow (listing SELL before HIRE, on the theory that a delayed sale is cheaper than a
    delayed hire) — this was a large, reproducible regression (~$50k → ~$37k, n=30 across 3
    opponents, confirmed twice): losing 1-2 HIRE entries to truncation costs that whole
    day's labor for every worker on the payroll, far more expensive than a sale sitting in
    the shed one extra hour. Reverted; the code comment now records the corrected reasoning.
11. **Nearest-actionable-tile targeting instead of fixed snake order (v16).** Constant sweeps
    had run dry (see the rejected list below), so instead of tuning another number, audited
    the actual per-action distribution over a full game: PASS was 46% of all worker-actions
    (mostly legitimate, see the idle-time entry below) but movement (WEST/NORTH/EAST/SOUTH
    combined) was 35% — more than the 18.5% spent on WATER/HARVEST/PLANT/DIG combined. The
    old `_next_target_in_band` walked the band in a fixed rotated-snake order and targeted
    the *first* actionable tile hit in that order, not necessarily the closest one to the
    worker's current position. Switched to picking the nearest actionable tile by Manhattan
    distance instead. ~$50.5k → ~$51.5k — validated with two independent n=15 batches on
    each side of the change (nearest-tile: $51,558 then $51,405; baseline: $50,528 then
    $50,420), the tight batch-to-batch agreement within each config being the main reason
    for confidence here (contrast the LIQUIDATION_DAYS entry below, where a $1,615
    batch-to-batch swing on one config was the tell that it was noise, not a real effect).

### Dropped or rejected (kept so they aren't re-litigated without new evidence)

- **Fertilizer, twice** — re-derived the yield math per crop instead of trusting a generic
  rejection: MELON and TOMATO already hit their yield cap via plain watering alone, but
  WHEAT's window is short enough (3 days) that it doesn't (`1+3*1=4` vs a cap of 6) — a
  genuine +50%/cycle opportunity. Built it properly for WHEAT (fixed two more real bugs:
  `PICKUP` only recognized one of four valid shed tiles, and hands don't exist in the
  observation until hour 1). Confirmed working end-to-end, still net-negative — the daily
  pickup trip costs more than the yield gain even where the math favors it.
- **Animal ranching (SHEEP)** — traced the CARE-bonus mechanic precisely and confirmed a real
  steady-state 3x production multiplier with full daily care. Built a dedicated rancher
  worker end-to-end (pasture, animal, daily feed/care, harvest/sell) — confirmed working,
  landed as a near miss (~$34.7k vs baseline). Escalating to 2 animals per rancher (to
  amortize the daily shed-trip cost) made it *worse*, not better, with far higher variance —
  the amortization hypothesis didn't hold.
- **WHEAT instead of MELON as the *sole* crop** — 25x lower base price isn't compensated by
  the faster cycle. (WHEAT as a *diversification* partner is the opposite result — a crop's
  solo value and its diversification value are genuinely different questions.)
- **STRAWBERRY instead of MELON** — weaker alone (~$20.5-22.2k).
- **Fewer hands during MELON's pre-harvest dry spell** — those early hands are doing
  essential planting/watering setup for tiles that mature later, not sitting idle.
- **NW/NE worker-pool reallocation** (`NW_WORKERS`, holding total hands at 9 — corrected
  finding, see the bug-fix commit) — the first pass at this sweep (NW=8/NE=1 through
  NW=4/NE=5) turned out to be contaminated: `_worker_quadrant_and_crop`'s old block-chunked
  assignment silently dropped any worker past the 3rd in NE to `(None, None, None)` rather
  than actually giving NE a 4th/5th worker, so "NW=6/NE=3" and smaller-NW configs were
  secretly still running NE at 3 workers plus one fully wasted (still paid for) hire — which
  is why that pass read as a flat tie instead of the real effect. After fixing the assignment
  logic (round-robin instead of fixed-block, see the commit), NE genuinely gets 4 workers at
  NW=6, and the corrected result is different: NW=6/NE=4 is clearly *worse* (n=15: mean
  $48,059, stdev $4,296 — both lower and far more volatile than baseline), while NW=8/NE=2
  needed two independent n=15 batches to resolve as a tie with baseline ($51,962 then
  $50,473, averaging to within noise of baseline's $51,481). Net conclusion is the same as
  before (NW=7/NE=3 stays optimal) but the *reason* isn't "division barely matters" — it's
  that NW's marginal worker (MELON's high per-unit price, big lumpy harvests) is worth more
  than NE's, so shrinking NW hurts, and there's no confirmed gain from growing NW further
  either.
- **CASH_RESERVE** (50/100/400/800 vs default 200) and **LAND_MIN_DAY** (1/2/5/7 vs default
  3) — both flat across the whole range tested, no signal above the ~$1-2k run-to-run noise.
- **NW's own crop mix, re-swept post-land-expansion** (3:2:2, 4:2:1, 5:1:1, 3:1:3, 4:0:3 vs
  default 4:1:2 MELON:TOMATO:WHEAT) — 5:1:1 looked promising on a quick 3-opponent pass
  (~$51.3k) but flattened to a dead heat at n=15 ($50,492 vs $50,528 baseline, stdev ~$3.5k);
  a caution about trusting the quick check alone. 3:2:2/3:1:3 (less MELON) were clearly
  worse; the original 4:1:2 remains the best confirmed mix even after land expansion changed
  everything else.
- **LIQUIDATION_DAYS** (1/5/7 vs default 3) and **LIQUIDATION_THROTTLE** (3/10 vs default 6)
  — LIQUIDATION_DAYS=1 looked like a real win on a first n=15 batch (mean $52,433, t≈1.9 vs
  baseline) but a second independent n=15 batch reverted to baseline ($50,818) — a clean
  example of why single-batch significance isn't enough at this variance level; two batches
  are now the minimum bar before trusting an n=15 result on this agent.
- **Worker idle-time audit** — instrumented every PASS action across a full game (46% of all
  worker-actions). 91% trace to workers whose whole band is genuinely still growing (nothing
  actionable exists yet); the remaining 9% all cluster in the season's final 4 days, where
  `_can_still_mature` is correctly refusing to plant anything that can't finish before day
  30 (the intended behavior from lever fix v12). No exploitable idle time found here — but
  the same audit's *movement*-share number is what led to lever 11 above.

Current results (`scripts/evaluate.py`, 10 episodes each, alternating sides), full 720-turn season:

| opponent | our mean $ | their mean $ | win rate |
|---|---|---|---|
| pass   | 51118 | 3000 | 10/10 |
| random | 50900 |   96 | 10/10 |
| starter| 51382 | 3543 | 10/10 |

v15 was confirmed with a 15-episode robustness check: mean $51,348, stdev $1,945 (~3.8%) —
nowhere near enough variance to explain the v14→v15 +9.2% jump by chance (t≈6.8). v16's
nearest-tile lever is backed by two independent n=15 batches per side instead (see lever 11)
rather than one larger batch, since that's what surfaced this session's single-batch false
alarm (LIQUIDATION_DAYS, above) in the first place.

Ten other independent parameters/structural choices (worker-pool split, CASH_RESERVE,
LAND_MIN_DAY, NW's crop mix, liquidation timing, hire/sell order priority, and worker
idle-time) came back flat, noise, or negative across two full rounds of testing before the
movement-targeting audit (lever 11) broke that streak. One of those ten — worker-pool
split — later turned out to have been tested on buggy code (a real assignment-overflow bug,
now fixed, that silently wasted any worker past the 3rd assigned to NE); re-run correctly, it
still doesn't beat the current default, but for a different, now-understood reason (see the
corrected entry above) rather than "division doesn't matter." The one remaining idea with
real (if likely small) potential is a restructured, non-additive multi-quadrant worker split
— so a second land quadrant (SW/SE) doesn't just dilute the existing ~9-hand budget the way
it did in the v13/v14 attempts — which would need further logic changes, not parameter
sweeps, to test properly.

Otherwise: the recorded-episode datasets on Kaggle/HF, for imitation learning as a possible
next direction beyond the rule-based approach.
