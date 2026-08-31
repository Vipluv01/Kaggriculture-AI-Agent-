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

v2 heuristic (`policy/heuristic.py`): farmer + up to 4 hired hands (re-hired every
morning — hands and hire cost both reset daily) each snake-scan their own band of tiles
in the starting quadrant, farming TOMATO (ongoing yield beats the built-in "starter"
baseline's one-shot CARROT loop). Submitted as `55918263`.

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
| pass   | 5785 | 3000 | 10/10 |
| random | 5815 |   21 | 10/10 |
| starter| 6199 | 3554 | 10/10 |

Next, if there's time: STRAWBERRY/animal income mix once capital allows (higher per-unit
price may sidestep TOMATO's price-saturation ceiling without needing more land), or the
recorded-episode datasets on Kaggle/HF for imitation learning if the heuristic plateaus.
