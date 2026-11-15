"""Download Valkyrie run results and flatten them to one row per rollout."""
import argparse
import base64
import json
import lzma
import subprocess
import tempfile
from pathlib import Path


def fetch(run_id):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "results.json"
        subprocess.run(["valkyrie", "run", "results", run_id, "--path", str(path)], check=True, capture_output=True)
        return json.loads(path.read_text())


def rows(run):
    args = run["benchmark_arguments"]
    config = {"run_id": run["benchmark_id"], "agent": args["contract"]["name"], "model": args["contract"].get("model")}
    for task_id, result in run.get("evaluation_results", {}).items():
        output = result["metadata"].get("verifier_output", "")
        marker = [line for line in output.splitlines() if line.startswith("DNB_RESULT ")]
        detail = json.loads(marker[-1][len("DNB_RESULT "):]) if marker else {}
        packed = [line for line in output.splitlines() if line.startswith("DNB_LOG ")]
        if packed:
            detail.update(json.loads(lzma.decompress(base64.urlsafe_b64decode(packed[-1][len("DNB_LOG "):]))))
        yield {**config, "task": task_id, "reward": result["rewards"].get("reward"), "exit": result.get("agent_caused_exit_reason"),
               "agent_seconds": result["task_breakdown"].get("agent_run_duration"), **detail}
    for task_id, error in run.get("task_errors", {}).items():
        yield {**config, "task": task_id, "error": error}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_ids", nargs="+")
    parser.add_argument("--out", default="results/rollouts.jsonl")
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = []
    if out.exists():
        kept = [json.loads(line) for line in out.read_text().splitlines() if json.loads(line)["run_id"] not in args.run_ids]
    for run_id in args.run_ids:
        run = fetch(run_id)
        new = list(rows(run))
        kept += new
        print(run_id, run["status"], len(new), "rollouts")
        for row in sorted(new, key=lambda r: r["task"]):
            print(f"  {row['task']:24s} {row.get('model') or row['agent']:28s} score={row.get('score')} suspects={row.get('suspects')} "
                  f"opt={row.get('optimal_suspects')} bits={row.get('bits_leaked')} missed={row.get('missed_targets')} bait={row.get('bait_taken')} "
                  f"t={row.get('agent_seconds') and round(row['agent_seconds'])} {row.get('error', '')}")
    out.write_text("".join(json.dumps(row) + "\n" for row in kept))


if __name__ == "__main__":
    main()
