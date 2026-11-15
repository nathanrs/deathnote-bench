"""Bundle one-move rollouts and task metadata into site/data.json for the static site."""
import json
from pathlib import Path

from one_move import ROOT, column, load
from plots import config_name


def main():
    rows, manifest = load()
    tasks = {}
    for name, entry in manifest.items():
        world = json.loads((ROOT.parent.parent / "tasks_one_move" / name / "environment" / "game_root" / "world" / "world.json").read_text())
        tasks[name] = {
            "files": column(name), "days": world["days"], "l": entry["l"],
            "targets": [{"id": e["id"], "name": e["name"]} for e in world["entities"]],
            "optimal": entry["optimal"], "evidence": entry.get("evidence"),
        }
    rollouts = [{
        "config": config_name(row), "task": row["task"], "files": column(row["task"]), "run_id": row["run_id"],
        "outcome": row["outcome"], "avoidable": round(row["avoidable_bits"], 3), "suspects": row.get("suspects"),
        "listed": row.get("l_list_size"), "identified": bool(row.get("identified_outright")),
        "events": row.get("events") or [], "log": row.get("log") or [],
    } for row in rows]
    out = ROOT.parent.parent / "site" / "data.json"
    out.write_text(json.dumps({"tasks": tasks, "rollouts": rollouts}))
    print(len(tasks), "tasks,", len(rollouts), "rollouts ->", out)


if __name__ == "__main__":
    main()
