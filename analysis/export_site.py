"""Bundle rollouts and task metadata into site/data.json for the static site."""
import argparse
import json
import math
from pathlib import Path

from plots import config_name, level_of, load


def task_info(task_dir, entry):
    world = json.loads((task_dir / "environment" / "game_root" / "world" / "world.json").read_text())
    return {
        "level": entry["level"], "template": entry["template"], "days": world["days"],
        "targets": [{"id": e["id"], "name": e["name"], "deadline": e["deadline"], "bait": e["is_bait"]} for e in world["entities"]],
        "news": world["news"], "optimal": entry["optimal"],
        "baselines": {name: entry[name] for name in ("naive", "static", "replan", "lookahead", "standard", "informed") if name in entry},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollouts", default="results/rollouts.jsonl")
    parser.add_argument("--tasks", default="tasks")
    parser.add_argument("--out", default="site/data.json")
    args = parser.parse_args()
    tasks_dir = Path(args.tasks)
    manifest = json.loads((tasks_dir / "manifest.json").read_text())
    tasks = {name: task_info(tasks_dir / name, entry) for name, entry in manifest.items()}
    rollouts = []
    rows, best = load(args.rollouts, manifest)
    for task, suspects in best.items():
        tasks[task]["optimal"] = {**tasks[task]["optimal"], "suspects": suspects, "bits": round(math.log2(10_000 / suspects), 3)}
    for row in rows:
        rollouts.append({
            "config": config_name(row), "task": row["task"], "level": level_of(row["task"]), "run_id": row["run_id"],
            "score": row.get("score") or 0.0, "passed": bool(row.get("passed")), "suspects": row.get("suspects"),
            "bits": row.get("bits_leaked"), "caught": bool(row.get("caught")), "missed": row.get("missed_targets") or [],
            "bait": row.get("bait_taken") or [], "events": row.get("events") or [], "log": row.get("log") or [],
            "error": row.get("error"), "seconds": row.get("agent_seconds"),
        })
    Path(args.out).write_text(json.dumps({"tasks": tasks, "rollouts": rollouts}))
    print(len(tasks), "tasks,", len(rollouts), "rollouts ->", args.out)


if __name__ == "__main__":
    main()
