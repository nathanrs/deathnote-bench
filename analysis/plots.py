"""Charts and the results table for the README, from results/rollouts.jsonl and tasks/manifest.json."""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
AGENT_NAMES = {"claude_code-v1.0.0": "Claude Code", "codex_dnb": "Codex", "toolloop": "no shell", "mini_swe_agent": "mini-SWE-agent"}


def config_name(row):
    model = (row.get("model") or "").split("/")[-1]
    return f"{model} · {AGENT_NAMES.get(row['agent'], row['agent'])}"


def level_of(task):
    return int(re.search(r"-l(\d+)-", task).group(1))


def load(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines()]
    return [row for row in rows if row["agent"] != "oracle"]


def by_level(rows):
    """config -> level -> list of scores; a rollout that errored counts as 0."""
    table = defaultdict(lambda: defaultdict(list))
    for row in rows:
        table[config_name(row)][level_of(row["task"])].append(row.get("score") or 0.0)
    return table


def baselines(manifest):
    table = defaultdict(lambda: defaultdict(list))
    for entry in manifest.values():
        for name in ("naive", "static", "replan"):
            table[name][entry["level"]].append(entry[name]["score"])
    return table


def mean(values):
    return sum(values) / len(values)


def style(ax, title, ylabel):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold", pad=12)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=9)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def score_by_level(table, base, out):
    fig, ax = plt.subplots(figsize=(9, 4.8), facecolor=SURFACE)
    levels = sorted({level for scores in table.values() for level in scores})
    reference = {"replan": ("patient re-planning script", "-"), "static": ("plan-once script", "--"), "naive": ("earliest-legal-move script", ":")}
    for name, (label, dash) in reference.items():
        if name in base:
            ax.plot(levels, [mean(base[name][level]) for level in levels], dash, color=MUTED, linewidth=1.2, label=label)
    for color, (config, scores) in zip(SERIES, sorted(table.items())):
        xs = [level for level in levels if level in scores]
        ax.plot(xs, [mean(scores[level]) for level in xs], "-o", color=color, linewidth=2, markersize=6, label=config)
    style(ax, "Score by level (1.0 = best possible plan, 0 = caught or target missed)", "mean score")
    ax.set_xticks(levels)
    ax.set_xticklabels([f"L{level}" for level in levels])
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=INK, loc="upper left", bbox_to_anchor=(1.01, 1))
    fig.tight_layout()
    fig.savefig(out, dpi=170, facecolor=SURFACE)
    plt.close(fig)


def bits_by_config(rows, out):
    excess = defaultdict(list)
    for row in rows:
        if row.get("bits_leaked") is not None and not row.get("missed_targets"):
            excess[config_name(row)].append(row["bits_leaked"] - row["optimal_bits"])
    names = sorted(excess, key=lambda name: mean(excess[name]))
    fig, ax = plt.subplots(figsize=(9, 0.55 * len(names) + 1.6), facecolor=SURFACE)
    values = [mean(excess[name]) for name in names]
    ax.barh(names, values, color=SERIES[0], height=0.55)
    for y, value in enumerate(values):
        ax.text(value + 0.05, y, f"{value:.2f}", va="center", color=INK, fontsize=9)
    style(ax, "Avoidable bits leaked per game (bits above the best possible plan)", "")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(out, dpi=170, facecolor=SURFACE)
    plt.close(fig)


def markdown_table(table, base):
    levels = sorted({level for scores in table.values() for level in scores})
    lines = ["| Configuration | " + " | ".join(f"L{level}" for level in levels) + " | Mean |", "|---|" + "---|" * (len(levels) + 1)]
    named = {"replan": "patient re-planning script", "static": "plan-once script", "naive": "earliest-legal-move script"}
    entries = sorted(table.items(), key=lambda item: -mean([s for v in item[1].values() for s in v]))
    entries += [(named[name], base[name]) for name in named if name in base]
    for config, scores in entries:
        cells = [f"{mean(scores[level]):.2f}" if level in scores else "–" for level in levels]
        overall = mean([s for values in scores.values() for s in values])
        lines.append(f"| {config} | " + " | ".join(cells) + f" | {overall:.2f} |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollouts", default="results/rollouts.jsonl")
    parser.add_argument("--manifest", default="tasks/manifest.json")
    parser.add_argument("--out", default="results")
    args = parser.parse_args()
    rows = load(args.rollouts)
    base = baselines(json.loads(Path(args.manifest).read_text()))
    table = by_level(rows)
    out = Path(args.out)
    score_by_level(table, base, out / "score_by_level.png")
    bits_by_config(rows, out / "avoidable_bits.png")
    (out / "table.md").write_text(markdown_table(table, base) + "\n")
    print(markdown_table(table, base))


if __name__ == "__main__":
    main()
