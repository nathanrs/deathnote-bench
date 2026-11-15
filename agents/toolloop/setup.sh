#!/bin/bash
set -euo pipefail
python3 -m venv /bundle/toolloop/.venv
/bundle/toolloop/.venv/bin/pip install --quiet anthropic==2.8.0 openai==3.51.0
chmod -R a+rX /bundle/toolloop
mkdir -p /logs
