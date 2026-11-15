import base64
import json
import lzma
import pickle
import sys
from pathlib import Path

sys.path.insert(0, "/opt/game")
from kira import trace  # noqa: E402

BLOB_LIMIT = 17_500  # Valkyrie keeps the last 20,000 characters of verifier output


def pack(record):
    return base64.urlsafe_b64encode(lzma.compress(json.dumps(record, separators=(",", ":")).encode())).decode()


world = json.loads(Path("/opt/game/world.json").read_text())
saved = Path("/opt/game/state/game.pkl")
game = pickle.loads(saved.read_bytes()) if saved.exists() else trace.Trace(**world["l"])
result = {"objective": world["objective"], "finished": game.over, **trace.summary(game, world["l"])}
result["score"] = round(result["points"] / result["informed_best"], 4)
Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
Path("/logs/verifier/reward.txt").write_text(str(result["score"]))
Path("/logs/verifier/details.json").write_text(json.dumps(result))
record = {"log": result.pop("log"), "briefings": result.pop("briefings")}
trims = [
    ("reasoning cut to 800 characters a day", lambda day: day.update(reasoning=day.get("reasoning", "")[:800])),
    ("reasoning dropped", lambda day: day.pop("reasoning", None)),
    ("notes cut to 600 characters a day", lambda day: day.update(notes_to_self=day.get("notes_to_self", "")[:600])),
]
result["log_trimmed"] = None
blob = pack(record)
for label, trim in trims:
    if len(blob) <= BLOB_LIMIT:
        break
    for day in record["log"]:
        trim(day)
    result["log_trimmed"], blob = label, pack(record)
print("DNB_LOG " + blob)
print("DNB_RESULT " + json.dumps(result))
