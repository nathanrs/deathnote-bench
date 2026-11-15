#!/bin/bash
# Re-download every run in results/runs.json, then rebuild the table, charts and site data.
cd "$(dirname "$0")/.."
.venv/bin/python analysis/collect.py $(.venv/bin/python -c "import json;print(' '.join(json.load(open('results/runs.json')).values()))") --out results/rollouts.jsonl > /dev/null
.venv/bin/python analysis/plots.py
