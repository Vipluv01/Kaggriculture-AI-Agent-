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

v8 heuristic (`policy/heuristic.py`) — current best, submitted. Progression:

| version | change | mean $ (10+ episodes/opponent) |
|---|---|---|
| v1 | single farmer, single quadrant, TOMATO | ~4.6-4.8k |
| v2 | +4 hired hands/day, band-patrol | ~5.8-6.2k |
| v3 | +dig & replant spent tiles | ~7.7-9.8k |
| v4 | **crop swap: MELON instead of TOMATO** + HANDS_CAP retuned to 6 | ~27.1k |
| v5 | +throttle SELL to 1 unit/turn instead of dumping the shed | ~27.6k |
| v6 | +CROP_MIX: split workers 5 MELON : 2 TOMATO | ~31.3k |
| v7 | **+3-way CROP_MIX: 5 MELON : 1 TOMATO : 1 WHEAT** | ~32.5k |
| v8 | +SEED_BUFFER_PER_WORKER retuned 2→1 for the 3-crop mix | **~32.9k** |

Real ladder scores (all `COMPLETE` as submitted; scores are a live skill rating against a
growing ~7000-team opponent pool, not raw dollars, and drift down over time for everyone
as that pool strengthens — same-window comparisons are what's meaningful): v1=267.1,
v2=263.3, v3=201.2, v4 climbed 372.7→441.4→439.7 then settled, v5=361.6, v6/v7 pending at
last check.

Four real levers found, each verified independently before being applied together:

1. **Crop choice.** MELON ($250 base, one-shot, max_yield=6) beats TOMATO ($60 base,
   ongoing, max_yield=4) by 3x+ alone, even though both cap out at a similar
   few-units-per-tile yield. Needed a real bug fix: a one-shot crop's tile starts at
   `yield_units=1` immediately on planting (`_new_plant`), so a naive "yield_units > 0
   means ripe" check fires HARVEST from turn one — the env silently no-ops that until
   `first_yield_day`, wasting turns that should've been spent watering for the
   bonus-yield window. Ripe now also gates on `age >= first_yield_day` for non-ongoing
   crops.
2. **Sell throttling.** MELON harvests land in large lumps (a worker's whole band
   matures together); dumping 30-85 units in one SELL order walks down the market's
   quadratic above-I0 price curve hard (an 85-unit dump nets ~$226 avg vs the $250 base,
   confirmed directly against `market_price()`). Throttling every SELL to 1 unit/turn was
   strictly better across every value swept (1/2/3/5/10/15/20/30) and still fully sells
   through by game end.
3. **Crop mix.** Even throttled, an all-MELON quadrant (~168 units/season) saturates
   MELON's own market on its own — logging the observed price at every sell showed it
   walking from ~$272 (early, scarcity premium) down to ~$51 (late, oversupply) over the
   course of one game. Splitting workers across MELON and TOMATO so production doesn't all
   land in one market pushed mean money from ~$27.6k to ~$31.3k. The ratio was swept
   empirically (not derivable analytically): 6:1 through 3:4, plus two 3-crop mixes adding
   STRAWBERRY. 5:2 MELON:TOMATO was a clear, non-monotonic peak — 6:1 actually scored
   *below* pure MELON.
4. **The right diversification partner isn't the best solo crop (the biggest lever of
   all).** WHEAT alone is a weak crop (25x lower base price than MELON, only compensated by
   a much faster cycle) — yet swapping it in as the *diversification* slice instead of
   TOMATO beat TOMATO's own mix (5:2 MELON:WHEAT ~$32.2k vs 5:2 MELON:TOMATO ~$31.3k), and
   a 3-way 5:1:1 MELON:TOMATO:WHEAT split beat both 2-crop mixes again (~$32.5k, then
   ~$32.9k after retuning `SEED_BUFFER_PER_WORKER` down to 1 for the new mix). Nearby
   ratios (4:1:2, 4:2:1) and a 4-crop spread (adding CARROT) all scored lower — one
   worker's worth of diversification, split across exactly two secondary crops, is the
   sweet spot found so far.

This last idea came from the competition's own official tutorial notebook
(`bovard/kaggriculture-getting-started`, pulled via `kaggle kernels pull`), which builds a
naive single-crop "Melon Maxxer" and calls out its exact weaknesses: no hired hands/land,
single-crop-only, no fertilizer, and dumping the whole shed in one sell. All four are now
addressed here (hands: implemented; land and fertilizer: implemented then evidence-based
rejected, not skipped; single-crop and dump-selling: fixed by levers 2 and 3 above).

Things tried and explicitly rejected (see the module docstring for full detail, so they
don't get re-litigated without new evidence):
- **Land expansion**, three times — v1 with no extra labor (lost money net), a fixed
  version with quadrant-scaled hiring under TOMATO (still worse than one quadrant), and
  retested under MELON specifically since its much higher per-unit price seemed like it
  might change the math — worse again, and by more: MELON's own 10-12 day pre-harvest dry
  spell compounds with a second quadrant's own ramp-up, leaving too little season left to
  pay back the capex.
- **Fertilizer** — implemented correctly (including fixing a bug where the generic
  "sell everything" loop was reselling it before a worker could pick it up), but its
  yield bonus is capped by the same `min(max_yield, ...)` as ordinary production — reaches
  the cap faster, never raises it. Net-negative once travel/purchase overhead is counted.
- **WHEAT instead of MELON as the *sole* crop** — much faster cycle (`first_yield_day`=2
  vs 10) but 25x lower base price isn't compensated by the extra cycles. (Notably, WHEAT
  as a *diversification partner* alongside MELON is the opposite result — see lever 4. A
  crop's solo value and its diversification value are genuinely different questions.)
- **STRAWBERRY instead of MELON, and as a third crop in the MELON:TOMATO mix** — weaker
  alone (~$20.5-22.2k) and underperformed the 2-crop 5:2 split (WHEAT, tried later, didn't).
- **Fewer hands during MELON's pre-harvest dry spell** — labor looked idle days 0-7 with
  no income yet, so tried a lower HANDS_CAP there; scored lower, not higher. Those early
  hands are doing essential planting/watering setup for tiles that mature later.
- **Nearby 3-crop ratios and a 4-crop spread** — 4:1:2 and 4:2:1 MELON:TOMATO:WHEAT, and a
  4-crop 4:1:1:1 spread adding CARROT, all scored below the 5:1:1 peak.
- **Re-swept HANDS_CAP and SELL_THROTTLE under the new crop mix** in case the optimum had
  shifted — both confirmed unchanged. `SEED_BUFFER_PER_WORKER` *did* shift (2→1), since 3
  crops now compete for seed capital.

Current results (`scripts/evaluate.py`, 10 episodes each, alternating sides), full 720-turn season:

| opponent | our mean $ | their mean $ | win rate |
|---|---|---|---|
| pass   | 32744 | 3000 | 10/10 |
| random | 32767 |   45 | 10/10 |
| starter| 33365 | 3598 | 10/10 |

(Unlike pure MELON, which was identical to 1 decimal across every run — verified via 20
independent random-seeded episodes with zero variance — the crop mix shows real but modest
variance across episodes: TOMATO and WHEAT, unlike MELON, are actively traded by other
agents/town shops, so opponent behavior and weed RNG now genuinely matter a little.
Confirmed with a 15-episode robustness check on v8: mean $32,892, stdev $372 (~1.1%).)

Next, if there's time: land expansion hasn't been retested since the crop mix changed the
income-timing picture (WHEAT's fast cycle means the farm no longer has a hard zero-income
ramp) — worth one more attempt given all three prior rejections assumed single-crop
economics. Otherwise, the recorded-episode datasets on Kaggle/HF for imitation learning.
