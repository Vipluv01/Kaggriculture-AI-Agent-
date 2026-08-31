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

v5 heuristic (`policy/heuristic.py`) — current best, submitted. Progression:

| version | change | mean $ (10 episodes/opponent) |
|---|---|---|
| v1 | single farmer, single quadrant, TOMATO | ~4.6-4.8k |
| v2 | +4 hired hands/day, band-patrol | ~5.8-6.2k |
| v3 | +dig & replant spent tiles | ~7.7-9.8k |
| v4 | **crop swap: MELON instead of TOMATO** + HANDS_CAP retuned to 6 | **~27.1k** |
| v5 | +throttle SELL to 1 unit/turn instead of dumping the shed | **~27.6k** |

Real ladder scores (all `COMPLETE`) track the local ranking: v1=267.1, v2=263.3, v3=201.2
(ladder scores are a live skill rating against a growing opponent pool, not raw dollars —
they drift down over time for everyone as the pool of ~7000 teams strengthens, so only
same-window comparisons are meaningful), v4=**372.7**, the best so far.

By far the biggest single lever was crop choice, not any behavioral change: MELON's base
price ($250) is ~4x TOMATO's ($60), and both crops cap out at a similar few-units-per-tile
total yield, so the higher-value crop wins by roughly that same multiple. Getting MELON
working correctly required fixing a real bug: a one-shot crop's tile starts at
`yield_units=1` immediately on planting (env internals, `_new_plant`), so a naive
"yield_units > 0 means ripe" check fires HARVEST from turn one — the env silently no-ops
that until `first_yield_day`, but every turn spent on a doomed HARVEST is a turn not spent
watering for the bonus-yield window. Ripe now also gates on `age >= first_yield_day` for
non-ongoing crops.

The second real lever: MELON harvests land in large lumps (a worker's whole band matures
together), and the original "sell everything in the shed" logic dumped 30-85 units into
one SELL order — walking down the market's quadratic above-I0 price curve hard (confirmed
directly against `market_price()`: an 85-unit dump nets ~$226 avg vs the $250 base).
Throttling every SELL to 1 unit/turn was strictly better across every value swept
(1/2/3/5/10/15/20/30 all tested) — and still fully sells through by game end (confirmed 0
units stranded in the shed at the final step), so it's a clean win with no tradeoff found.

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
- **WHEAT instead of MELON** — much faster cycle (`first_yield_day`=2 vs 10) but 25x
  lower base price ($25 vs $250) isn't compensated by the extra cycles.

Current results (`scripts/evaluate.py`, 10 episodes each, alternating sides), full 720-turn season:

| opponent | our mean $ | their mean $ | win rate |
|---|---|---|---|
| pass   | 27566 | 3000 | 10/10 |
| random | 27566 |   97 | 10/10 |
| starter| 27566 | 3556 | 10/10 |

(Our mean is identical to 1 decimal across opponents/episodes — verified this isn't a bug:
neither the opponent's actions nor weed-spawn RNG meaningfully touch MELON's economics,
since opponents mostly trade other goods.)

Next, if there's time: try STRAWBERRY (also one-shot-adjacent pricing tier, $120 base) or
MELON+TOMATO mixed planting to smooth the ~10-day zero-income ramp before the first
harvest; or the recorded-episode datasets on Kaggle/HF for imitation learning.
