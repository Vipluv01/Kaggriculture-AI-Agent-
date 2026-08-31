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

v4 heuristic (`policy/heuristic.py`) — current best, submitted. Progression:

| version | change | mean $ (10 episodes/opponent) |
|---|---|---|
| v1 | single farmer, single quadrant, TOMATO | ~4.6-4.8k |
| v2 | +4 hired hands/day, band-patrol | ~5.8-6.2k |
| v3 | +dig & replant spent tiles | ~7.7-9.8k |
| v4 | **crop swap: MELON instead of TOMATO** + HANDS_CAP retuned to 6 | **~27k** |

By far the biggest single lever was crop choice, not any behavioral change: MELON's base
price ($250) is ~4x TOMATO's ($60), and both crops cap out at a similar few-units-per-tile
total yield, so the higher-value crop wins by roughly that same multiple. Real ladder
scores confirm the trend so far: v1 scored 328.2, v2 scored 600.0 (both `COMPLETE`).

Getting MELON working correctly required fixing a real bug: a one-shot crop's tile starts
at `yield_units=1` immediately on planting (env internals, `_new_plant`), so a naive
"yield_units > 0 means ripe" check fires HARVEST from turn one — the env silently no-ops
that until `first_yield_day`, but every turn spent on a doomed HARVEST is a turn not spent
watering for the bonus-yield window. Ripe now also gates on `age >= first_yield_day` for
non-ongoing crops.

Two things tried and explicitly rejected (see the module docstring for full detail, so
they don't get re-litigated without new evidence):
- **Land expansion**, twice — even after fixing a real cash-reserve bug on the second
  attempt, it scored lower than staying in the single starting quadrant. Market price
  decays with supply and land capex doesn't pay back inside a 30-day season.
- **Fertilizer** — implemented correctly (including fixing a bug where the generic
  "sell everything in the shed" loop was reselling the fertilizer before a worker could
  pick it up), but re-reading the env source showed its yield bonus is capped by the same
  `min(max_yield, ...)` as ordinary production — it only reaches the cap *faster*, never
  raises it. Net-negative once travel/purchase overhead is counted.

Current results (`scripts/evaluate.py`, 10 episodes each, alternating sides), full 720-turn season:

| opponent | our mean $ | their mean $ | win rate |
|---|---|---|---|
| pass   | 27073 | 3000 | 10/10 |
| random | 27073 |   59 | 10/10 |
| starter| 27073 | 3551 | 10/10 |

(Our mean is identical to 1 decimal across opponents/episodes — verified this isn't a bug:
MELON revenue is dominated by two large lump-sum harvest+sell waves around day 12 and day
22, and neither the opponent's actions nor weed-spawn RNG meaningfully perturb that.)

Next, if there's time: try STRAWBERRY (also one-shot-adjacent pricing tier, $120 base) or
MELON+TOMATO mixed planting to smooth the ~10-day zero-income ramp before the first
harvest; or the recorded-episode datasets on Kaggle/HF for imitation learning.
