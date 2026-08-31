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

v3 heuristic (`policy/heuristic.py`): v2 (farmer + up to 4 hired hands, re-hired every
morning since hands and hire cost both reset daily, each snake-scanning their own band of
the starting quadrant) plus digging and replanting spent tiles. TOMATO is "ongoing" but
not infinite — it produces for exactly 4 ticks starting 8 days after planting, then stops
producing forever and just decays into a weed if left alone. v2 never dug a spent tile, so
most tiles only got farmed once across the whole 30-day season; v3 detects
`day - planted_day >= 11` (all 4 ticks used) or an actual weed tile and digs it to replant.
That alone was worth ~$2k in mean final money (see table) — bigger than any of the
land-expansion attempts below.

Land expansion was tried **twice** and dropped both times:
- v1 bought land with no extra labor to work it — lost money net (unwatered tiles ->
  weeds -> wasted seed cost, land cost itself ate working capital).
- A v3 attempt paired land with hiring scaled to quadrants owned, and fixed a real bug
  along the way (it kept hiring even at near-zero money, starving out seed restocking
  and spiraling down) — but even fixed, it scored *lower* than staying single-quadrant
  with hands maxed out (~$5.2-5.4k vs ~$6.2-6.5k). The market's price decays with supply
  (TOMATO's curve saturates around 200 units/24 days) and land capex doesn't pay back
  inside a 30-day season. Documented as a dead end in the module docstring, not a TODO.

Current results (`scripts/evaluate.py`, 10 episodes each, alternating sides), full 720-turn season:

| opponent | our mean $ | their mean $ | win rate |
|---|---|---|---|
| pass   | 8201 | 3000 | 10/10 |
| random | 7748 |   10 | 10/10 |
| starter| 8010 | 3472 | 10/10 |

Next, if there's time: STRAWBERRY/animal income mix once capital allows (higher per-unit
price may sidestep TOMATO's price-saturation ceiling without needing more land), or the
recorded-episode datasets on Kaggle/HF for imitation learning if the heuristic plateaus.
