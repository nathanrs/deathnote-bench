#!/bin/bash
# Prints the labels of every in-progress Valkyrie run, one per line.
valkyrie run list --status in_progress --all --format json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
runs = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
for run in runs:
    print(run.get('label') or run.get('labels') or run.get('id'))
"
