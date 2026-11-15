import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, "/opt/game")
from kira import trace  # noqa: E402

world = json.loads(Path("/opt/game/world.json").read_text())
saved = Path("/opt/game/state/game.pkl")
game = pickle.loads(saved.read_bytes()) if saved.exists() else trace.Trace(**world["l"])
result = {"objective": world["objective"], "finished": game.over, **trace.summary(game, world["l"])}
result["score"] = round(result["points"] / result["informed_best"], 4)
Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
Path("/logs/verifier/reward.txt").write_text(str(result["score"]))
Path("/logs/verifier/details.json").write_text(json.dumps(result))
print("DNB_RESULT " + json.dumps(result))
