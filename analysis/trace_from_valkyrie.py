"""Download tracing-game runs from Valkyrie and write one game file per rollout, in the local runner's format.

usage: trace_from_valkyrie.py OUT_DIR EFFORT RUN_ID [RUN_ID ...]"""
import json
import sys
from pathlib import Path

from collect import fetch, rows


def main(out_dir, effort, run_ids):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for run_id in run_ids:
        run = fetch(run_id)
        done = failed = 0
        for row in rows(run):
            if "points" not in row:
                failed += 1
                print("  no game record:", row.get("model"), row["task"], str(row.get("error") or row.get("exit"))[:100])
                continue
            if not row["finished"]:
                print(f"  stopped on day {row['days']} with {row['points']} points:", row["model"], row["task"], row.get("exit"))
            done += 1
            name = f"{row['model'].split('/')[-1]}_w{row['world']['seed']}.json"
            (out / name).write_text(json.dumps({**row, "effort": effort}, indent=1))
        print(run_id, run["status"], f"{done} games, {failed} failed")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
