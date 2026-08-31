"""Run the heuristic agent against each baseline over several episodes and
report mean final money + win rate, alternating which side it plays."""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kaggle_environments import make

from policy.heuristic import agent

BASELINES = ["pass", "random", "starter"]
EPISODES_PER_SIDE = 5
EPISODE_STEPS = 720


def run(opponent, our_index):
    agents = [agent, opponent] if our_index == 0 else [opponent, agent]
    env = make("kaggriculture", configuration={"episodeSteps": EPISODE_STEPS}, debug=False)
    env.run(agents)
    final = env.steps[-1]
    return final[our_index]["reward"], final[1 - our_index]["reward"]


def main():
    for opponent in BASELINES:
        ours, theirs, wins = [], [], 0
        for side in (0, 1):
            for _ in range(EPISODES_PER_SIDE):
                us, them = run(opponent, side)
                ours.append(us)
                theirs.append(them)
                wins += us > them
        n = len(ours)
        print(
            f"vs {opponent:8s}  our_mean=${statistics.mean(ours):8.1f}  "
            f"their_mean=${statistics.mean(theirs):8.1f}  win_rate={wins}/{n}"
        )


if __name__ == "__main__":
    main()
