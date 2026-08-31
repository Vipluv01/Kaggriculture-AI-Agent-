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

Requires a Kaggle API token (`~/.kaggle/kaggle.json`) and having joined the competition
(accept rules on the competition page) first.

```bash
.venv/bin/kaggle competitions submit kaggriculture -f main.py -m "message"
```

## Status

v1 heuristic (`policy/heuristic.py`): single farmer, snake-scans the NW quadrant, plants
TOMATO (ongoing yield beats the built-in "starter" baseline's one-shot CARROT loop),
waters/harvests/sells opportunistically. Deliberately does **not** buy land or hire hands
yet — an earlier version did, and measurably lost: more tiles than one farmer can water
daily means weeds, i.e. wasted seed money, and the land purchase itself ($1k/$2k/$4k) ate
into working capital faster than the extra tiles paid it back. Land/hands need to be
bought *together* (hands to work the new land) — that's the next real increment.

Current results (`scripts/evaluate.py`, 10 episodes each, alternating sides), full 720-turn season:

| opponent | our mean $ | their mean $ | win rate |
|---|---|---|---|
| pass   | 4594 | 3000 | 10/10 |
| random | 4760 |   60 | 10/10 |
| starter| 4568 | 3556 | 10/10 |

Next: expand land + hire hands in lockstep, consider STRAWBERRY/animal income once
capital allows, then look at the recorded-episode datasets on Kaggle/HF for imitation
learning if the heuristic plateaus. Kaggle submission (`kaggle competitions submit`)
still needs an API token at `~/.kaggle/kaggle.json` — not set up on this machine yet.
