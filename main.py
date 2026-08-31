"""Kaggriculture submission entrypoint.

For local dev this just re-exports policy/heuristic.py. Kaggle's runner needs
either a single self-contained file or a submission.tar.gz with main.py at
the root — when we're ready to submit, bundle this file together with
policy/ into that tar.gz (see README) rather than inlining everything here.

Note: the package holding the policy is deliberately NOT named "agents" --
kaggle_environments does its own sys.path/sys.modules manipulation when
loading built-in envs (e.g. lux_ai_s3 has its own internal agents.py), and a
top-level "agents" package here collides with that and breaks imports.
"""

from policy.heuristic import agent  # noqa: F401 -- entrypoint kaggle-environments looks up
