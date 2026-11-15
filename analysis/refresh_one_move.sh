#!/bin/bash
# Re-download every one-move run, then rebuild its table and charts.
cd "$(dirname "$0")/.."
.venv/bin/python analysis/collect.py $(.venv/bin/python -c "import json;print(' '.join(json.load(open('results/one_move/runs.json')).values()))") --out results/one_move/rollouts.jsonl > /dev/null
.venv/bin/python analysis/one_move.py
.venv/bin/python analysis/export_site.py
