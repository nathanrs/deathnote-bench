import json
import sys
from pathlib import Path

sys.path.insert(0, "/opt/game")
from deathnotebench.core import Game, World, grade  # noqa: E402

world = World.load("/opt/game/world")
state_path = Path("/opt/game/state/state.json")
state = json.loads(state_path.read_text()) if state_path.exists() else Game(world).state
result = grade(world, state)
Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
Path("/logs/verifier/reward.txt").write_text(str(result["score"]))
Path("/logs/verifier/details.json").write_text(json.dumps(result))
print("DNB_RESULT " + json.dumps(result))
