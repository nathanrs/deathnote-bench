"""Write one Valkyrie task per hidden L."""
import argparse
import itertools
import json
import shutil
from pathlib import Path

from .trace import KINDS, make_world

HERE = Path(__file__).resolve().parent
SANDBOX = HERE / "sandbox"


def write_task(seed, out, objective):
    task = Path(out) / f"trace-{seed:03d}"
    if task.exists():
        shutil.rmtree(task)
    root = task / "environment" / "game_root"
    (root / "kira").mkdir(parents=True)
    (root / "kira" / "__init__.py").write_text("")
    shutil.copy(HERE / "trace.py", root / "kira" / "trace.py")
    for name in ("server.py", "grade_cli.py", "start.sh", "game"):
        shutil.copy(SANDBOX / name, root / name)
    pairs = list(itertools.combinations(KINDS, 2))
    (root / "world.json").write_text(json.dumps({"l": make_world(seed, pairs[(seed - 1) % len(pairs)]), "objective": objective}))
    shutil.copy(SANDBOX / "Dockerfile", task / "environment" / "Dockerfile")
    (task / "tests").mkdir()
    shutil.copy(SANDBOX / "test.sh", task / "tests" / "test.sh")
    (task / "solution").mkdir()
    shutil.copy(SANDBOX / "instruction.md", task / "instruction.md")
    (task / "task.toml").write_text((SANDBOX / "task.toml").read_text().format(seed=seed))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="tasks_trace")
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--no-objective", action="store_true")
    args = parser.parse_args()
    for seed in args.seeds:
        write_task(seed, args.out, not args.no_objective)
    shutil.copy(HERE / "llm.py", HERE.parent / "agents" / "lightloop" / "llm.py")
    print(len(args.seeds), "tasks ->", args.out)


if __name__ == "__main__":
    main()
