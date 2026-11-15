"""The game inside the sandbox. Root owns the hidden L; the player reaches it only through `game`."""
import json
import pickle
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, "/opt/game")
from kira import trace  # noqa: E402

ROOT = Path("/opt/game")
SAVED = ROOT / "state" / "game.pkl"
WORLD = json.loads((ROOT / "world.json").read_text())
USAGE = """\
usage:
  game rules          the rules of the game
  game view           today's situation as JSON; "over" is true once the game has ended
  game play 'JSON'    end the day with {"notes_to_self": "...", "kills": [{"criminal": "d1-3", "entry": "quick", "block": "morning"}]}"""


def run(argv):
    game = pickle.loads(SAVED.read_bytes()) if SAVED.exists() else trace.Trace(**WORLD["l"])
    if argv == ["rules"]:
        return True, trace.rules_text(WORLD["l"], WORLD["objective"])
    if argv == ["view"]:
        return True, json.dumps({"over": game.over, **({} if game.over else trace.player_view(game))})
    if len(argv) == 2 and argv[0] == "play":
        if game.over:
            return False, "The game is over."
        try:
            reply = json.loads(argv[1])
        except json.JSONDecodeError as error:
            return False, f"Not played: that is not valid JSON ({error})."
        trace.take_turn(game, reply if isinstance(reply, dict) else {})
        SAVED.write_bytes(pickle.dumps(game))
        return True, json.dumps({"over": game.over, "problems_with_your_entries": game.problems})
    return False, USAGE


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        ok, text = run(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"ok": ok, "text": text}).encode())

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 7777), Handler).serve_forever()
