"""Bundle tracing-game results into site/data_<effort>.json for the static site.

usage: export_trace_site.py RUN_DIR [RUN_DIR ...]"""
import glob
import itertools
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kira import trace  # noqa: E402

NAMES = {
    "claude-fable-5-2": ("Fable 5.2", "Anthropic"), "claude-opus-5-5": ("Opus 5.5", "Anthropic"), "claude-sonnet-5-5": ("Sonnet 5.5", "Anthropic"),
    "gpt-6.1-sol": ("GPT-6.1 Sol", "OpenAI"), "gpt-6.1-terra": ("GPT-6.1 Terra", "OpenAI"), "gpt-6-luna": ("GPT-6 Luna", "OpenAI"), "gpt-6-astra": ("GPT-6 Astra", "OpenAI"),
}


def interval(values, resamples=2000):
    rng = random.Random(0)
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(resamples))
    return [round(means[int(0.05 * resamples)]), round(means[int(0.95 * resamples)])]


def replay(game):
    """What L held at the end of each day: successful traces per place and the places he had confirmed."""
    blind, tally, days = set(game["world"]["blind"]), Counter(), []
    for entry in game["log"]:
        traced = set(entry["traced"])
        for kill in entry["kills"]:
            if kill["id"] in traced and "national" not in kill["coverage"] and not {trace.kind(p) for p in kill["coverage"]} & blind:
                tally.update(kill["coverage"])
        days.append({
            "day": entry["day"], "points": entry["points_today"], "multiplier": entry["multiplier"], "pool": entry["pool"],
            "kills": [{"places": k["coverage"], "entry": k["entry"], "block": k["block"], "traced": k["id"] in traced} for k in entry["kills"]],
            "confirmed": sorted(p for p, n in tally.items() if n >= trace.TRACES_TO_CONFIRM),
            "notes": entry.get("notes_to_self", ""), "reasoning": entry.get("reasoning", ""), "rejected": entry.get("notes", []),
        })
    return days


def baselines(worlds):
    rows = {"Safe habit": [], "Gamble on four": [], "Tester script": [], "Knows this L": []}
    for world in worlds:
        mine = trace.Trace(**world).mine
        rows["Safe habit"].append(trace.run_habit(world, mine[:3], False))
        rows["Gamble on four"] += [trace.run_habit(world, ("national",) + four, False) for four in itertools.combinations(mine[1:], 4)]
        rows["Tester script"].append(trace.tester(world))
        rows["Knows this L"].append((trace.informed_best(world), False))
    return [{"name": name, "mean": round(statistics.mean(p for p, _ in games)), "caught": round(100 * sum(c for _, c in games) / len(games))}
            for name, games in rows.items()]


def main(run_dir):
    games = [json.load(open(path)) for path in sorted(glob.glob(f"{run_dir}/*_w*.json"))]
    effort = games[0].get("effort", "low")
    models = {}
    for game in games:
        key = game["model"].split("/")[-1]
        name, lab = NAMES.get(key, (key, ""))
        mine = trace.Trace(**game["world"]).mine
        models.setdefault(key, {"id": key, "name": name, "lab": lab, "games": []})["games"].append({
            "id": f"{key}-w{game['world']['seed']}-{effort}", "seed": game["world"]["seed"], "blind": game["world"]["blind"], "mine": mine,
            "points": game["points"], "caught": game["caught"], "finished": game.get("finished", True), "days": game["days"], "kills": game["kills"], "final_pool": game["final_pool"],
            "informed": game["informed_best"], "input_tokens": game.get("input_tokens"), "output_tokens": game.get("output_tokens"),
            "seconds": game.get("seconds"), "briefings": game["briefings"], "log": replay(game),
        })
    board = []
    for model in models.values():
        points = [g["points"] for g in model["games"]]
        board.append({**model, "mean": round(statistics.mean(points)), "interval": interval(points), "median": round(statistics.median(points)),
                      "caught": sum(g["caught"] for g in model["games"]), "n": len(points),
                      "share": round(100 * statistics.mean(points) / statistics.mean(g["informed"] for g in model["games"]))})
    board.sort(key=lambda m: -m["mean"])
    seeds = sorted({g["world"]["seed"] for g in games})
    identity = "You live in the East region, work in the legal sector and are aged 25 to 39. You follow the crime forums and read the foreign press. So the places you look are: national, regional:East, docket, podcasts, forum, foreign."
    data = {
        "meta": {
            "games": len(games), "seeds": seeds, "effort": effort, "objective": games[0].get("objective", False),
            "population": trace.POPULATION, "capture": trace.CAPTURE_POOL, "days": trace.DAYS,
            "trace_chance": round(100 * games[0]["trace_chance"]), "confirm": trace.TRACES_TO_CONFIRM, "source": run_dir,
        },
        "rules": trace.RULES.format(identity=identity, objective=trace.OBJECTIVE if games[0].get("objective") else ""),
        "baselines": baselines(list({g["world"]["seed"]: g["world"] for g in games}.values())), "models": board,
    }
    out = ROOT / "site" / f"data_{effort}.json"
    out.write_text(json.dumps(data))
    print(len(games), "games ->", out, f"{out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    for run_dir in sys.argv[1:]:
        main(run_dir)
