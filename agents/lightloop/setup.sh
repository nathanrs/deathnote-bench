#!/bin/bash
set -euo pipefail
python3 -m venv /bundle/lightloop/.venv
/bundle/lightloop/.venv/bin/pip install --quiet anthropic==2.8.0 openai==3.51.0
chmod -R a+rX /bundle/lightloop
mkdir -p /logs
