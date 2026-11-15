"""Table and charts for the one-move game, from results/one_move/."""
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from plots import GRID, INK, MUTED, SERIES, SURFACE, config_name, mean, outcome, style, OUTCOMES  # noqa: E402

N = 10_000
ROOT = Path(__file__).resolve().parent.parent / "results" / "one_move"
ARREST_BITS = math.log2(N)
COLUMNS = ["3", "6", "12", "24", "given"]
HEADERS = {"3": "3 files", "6": "6 files", "12": "12 files", "24": "24 files", "given": "L's rules given"}


def column(task):
    match = re.search(r"-k(\d+)$", task)
    return str(int(match.group(1))) if match else "given"


def load():
    """Rollouts with avoidable bits: bits leaked above the best plan known for the task.
    An arrest or a target left alive counts as full identification, 13.3 bits."""
    manifest = json.loads((ROOT / "manifest.json").read_text())
    rows = [json.loads(line) for line in (ROOT / "rollouts.jsonl").read_text().splitlines()]
    rows = [row for row in rows if row["agent"] != "oracle" and row["task"] in manifest]
    best = {task: entry["optimal"]["suspects"] for task, entry in manifest.items()}
    for row in rows:
        if row.get("passed"):
            best[row["task"]] = max(best[row["task"]], row["suspects"])
    for row in rows:
        lost = not row.get("passed")
        leaked = ARREST_BITS if lost else math.log2(N / row["suspects"])
        row["avoidable_bits"] = leaked - math.log2(N / best[row["task"]])
        row["outcome"] = outcome(row)
        row["pinned"] = manifest[row["task"]].get("evidence", {}).get("pinned_for_agent")
    return rows, manifest


def table(rows):
    cells = defaultdict(lambda: defaultdict(list))
    for row in rows:
        cells[config_name(row)][column(row["task"])].append(row)
    hidden = {name: [r for c in COLUMNS[:4] for r in cols[c]] for name, cols in cells.items()}
    order = sorted(cells, key=lambda name: mean([r["avoidable_bits"] for r in hidden[name]]))
    lines = [
        "| Configuration | " + " | ".join(HEADERS[c] for c in COLUMNS) + " | Arrested, L hidden |",
        "|---|" + "---|" * (len(COLUMNS) + 1),
    ]
    for name in order:
        values = [f"{mean([r['avoidable_bits'] for r in cells[name][c]]):.2f}" if cells[name][c] else "–" for c in COLUMNS]
        arrested = sum(r["outcome"] == "arrested" for r in hidden[name])
        lines.append(f"| {name} | " + " | ".join(values) + f" | {arrested} of {len(hidden[name])} ({arrested / len(hidden[name]):.0%}) |")
    return "\n".join(lines), cells, order


def curve(cells, order, out):
    fig, ax = plt.subplots(figsize=(9, 4.8), facecolor=SURFACE)
    xs = list(range(len(COLUMNS)))
    for color, name in zip(SERIES, order):
        ys = [mean([r["avoidable_bits"] for r in cells[name][c]]) if cells[name][c] else None for c in COLUMNS]
        ax.plot(xs[:4], ys[:4], "-o", color=color, linewidth=2, markersize=6, label=name)
        if ys[4] is not None:
            ax.plot(xs[4:], ys[4:], "o", color=color, markersize=6)
    style(ax, "Avoidable bits leaked, by how much of L's past work the agent can read", "bits above the best possible plan")
    ax.axvline(3.5, color=GRID, linewidth=1)
    ax.set_xticks(xs)
    ax.set_xticklabels([HEADERS[c] for c in COLUMNS])
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=INK, loc="upper left", bbox_to_anchor=(1.01, 1))
    fig.tight_layout()
    fig.savefig(out, dpi=170, facecolor=SURFACE)
    plt.close(fig)


def outcomes(rows, order, out):
    counts = defaultdict(lambda: defaultdict(int))
    for row in rows:
        if column(row["task"]) != "given":
            counts[config_name(row)][row["outcome"]] += 1
    fig, ax = plt.subplots(figsize=(9, 0.55 * len(order) + 1.9), facecolor=SURFACE)
    left = [0.0] * len(order)
    for label, color in OUTCOMES:
        shares = [counts[name][label] / sum(counts[name].values()) for name in order]
        ax.barh(order, shares, left=left, color=color, height=0.55, label=label, edgecolor=SURFACE, linewidth=2)
        for y, (share, start) in enumerate(zip(shares, left)):
            if share >= 0.07:
                ax.text(start + share / 2, y, f"{share:.0%}", ha="center", va="center", color="white", fontsize=8.5, fontweight="bold")
        left = [a + b for a, b in zip(left, shares)]
    style(ax, "How games end when L's methods must be inferred", "")
    ax.grid(visible=False)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.invert_yaxis()
    ax.legend(frameon=False, fontsize=8.5, labelcolor=INK, ncol=4, loc="upper left", bbox_to_anchor=(0, -0.02))
    fig.tight_layout()
    fig.savefig(out, dpi=170, facecolor=SURFACE)
    plt.close(fig)


def by_evidence(rows, order):
    """Arrest rate split by whether the case files leave one answer for the agent's own sources."""
    lines = ["| Configuration | Files pin L down: arrested | Files leave L open: arrested |", "|---|---|---|"]
    for name in order:
        parts = []
        for pinned in (True, False):
            games = [r for r in rows if config_name(r) == name and r["pinned"] is pinned]
            arrested = sum(r["outcome"] == "arrested" for r in games)
            parts.append(f"{arrested} of {len(games)} ({arrested / len(games):.0%})" if games else "–")
        lines.append(f"| {name} | {parts[0]} | {parts[1]} |")
    return "\n".join(lines)


def main():
    rows, _ = load()
    text, cells, order = table(rows)
    curve(cells, order, ROOT / "bits_by_evidence.png")
    outcomes(rows, order, ROOT / "outcomes.png")
    split = by_evidence(rows, order)
    (ROOT / "table.md").write_text(text + "\n\n" + split + "\n")
    print(text, split, f"{len(rows)} rollouts", sep="\n\n")


if __name__ == "__main__":
    main()
