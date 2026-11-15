#!/bin/bash
if ! curl -s -m 2 http://127.0.0.1:7777/ >/dev/null; then
  nohup setsid python3 /opt/game/server.py >/opt/game/state/server.log 2>&1 &
  sleep 2
fi
curl -s -m 2 http://127.0.0.1:7777/ >/dev/null
