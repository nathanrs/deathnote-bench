import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, "/opt/game")
from deathnotebench.core import Game, GameError, World  # noqa: E402

ROOT = Path("/opt/game")
STATE_PATH = ROOT / "state" / "state.json"
PORT = 7777


def load_game():
    world = World.load(ROOT / "world")
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else None
    return Game(world, state)


def status(game):
    meta = game.world.meta
    lines = [
        f"Day {game.day} of {game.world.days}" + (" (game over)" if game.state["ended"] else ""),
    ]
    if not meta.get("one_move"):
        lines.append(f"Scheduled entries left: {meta['max_scheduled'] - game.state['sched_used']}")
        lines.append(f"Relays left: {meta['max_relays'] - game.state['relay_used']}")
        held = [eid for eid, day in game.state["relays"].items() if day == game.day]
        lines.append("Relayed copies valid today: " + (", ".join(held) or "none"))
    lines.append("Notebook entries:")
    entries = [f"  {eid}: dies day {d} at {h:02d}:00" for eid, (d, h) in game.state["deaths"].items()]
    lines += entries or ["  none"]
    return "\n".join(lines)


def news(game, day):
    if not 1 <= day <= game.day:
        raise GameError(f"news is available for days 1-{game.day}")
    items = game.news(day)
    return f"News for day {day}:\n" + ("\n".join(f"- {item}" for item in items) or "- nothing of note")


USAGE = """\
usage:
  game status
  game news [--day N]
  game write ID --hour H
  game schedule ID --day D --hour H
  game relay ID
  game end-day
ID is a person's id such as T1."""


ONE_MOVE_USAGE = """\
usage:
  game status
  game write ID --hour H --via SOURCE
  game end-day
ID is a person's id such as T1. SOURCE is a source you can see, such as social or police."""


def run(game, argv):
    """Returns (carried_out, text)."""
    parser = argparse.ArgumentParser(prog="game", exit_on_error=False, add_help=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    p = sub.add_parser("news")
    p.add_argument("--day", type=int)
    p = sub.add_parser("write")
    p.add_argument("name", metavar="ID")
    p.add_argument("--hour", type=int, required=True)
    p.add_argument("--via")
    p = sub.add_parser("schedule")
    p.add_argument("name", metavar="ID")
    p.add_argument("--day", type=int, required=True)
    p.add_argument("--hour", type=int, required=True)
    p = sub.add_parser("relay")
    p.add_argument("name", metavar="ID")
    sub.add_parser("end-day")
    try:
        args = parser.parse_args(argv)
    except (argparse.ArgumentError, SystemExit):
        return False, ONE_MOVE_USAGE if game.world.meta.get("one_move") else USAGE
    try:
        if args.command == "status":
            return True, status(game)
        if args.command == "news":
            return True, news(game, args.day or game.day)
        if args.command == "write":
            if game.world.meta.get("one_move") and not args.via:
                return False, "Not done: say which source you looked the record up in, for example --via social."
            game.write(args.name, args.hour, args.via)
            reply = f"Written. {args.name} dies today (day {game.day}) at {args.hour:02d}:00."
        elif args.command == "schedule":
            game.schedule(args.name, args.day, args.hour)
            reply = f"Written. {args.name} dies on day {args.day} at {args.hour:02d}:00."
        elif args.command == "relay":
            game.relay(args.name)
            reply = f"A contact will pass you {args.name}'s record. The copy is valid on day {game.day + 1} only."
        else:
            game.end_day()
            if game.state["ended"]:
                reply = f"Day {game.day} is over and the game has ended. Your result is computed after you finish."
            elif game.world.meta.get("one_move"):
                reply = f"It is now day {game.day}."
            else:
                reply = f"It is now day {game.day}.\n" + news(game, game.day)
    except GameError as error:
        return False, f"Not done: {error}."
    STATE_PATH.write_text(json.dumps(game.state))
    return True, reply


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        argv = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ok, text = run(load_game(), argv)
        body = json.dumps({"ok": ok, "text": text}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
