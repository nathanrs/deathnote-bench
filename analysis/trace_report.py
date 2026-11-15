"""Table and charts for the tracing game.

usage: trace_report.py RUN_DIR [RUN_DIR ...]   (first directory is the main leaderboard; charts go next to it)"""
import glob
import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_trace_site import NAMES, baselines, interval  # noqa: E402
from plots import GRID, INK, MUTED, SURFACE  # noqa: E402

LAB = {"Anthropic": "#c2693f", "OpenAI": "#2a78d6"}


def load(run_dir):
    by_model = {}
    for path in sorted(glob.glob(f"{run_dir}/*_w*.json")):
        game = json.load(open(path))
        by_model.setdefault(game["model"].split("/")[-1], []).append(game)
    rows = []
    for key, games in by_model.items():
        points = [g["points"] for g in games]
        name, lab = NAMES.get(key, (key, ""))
        rows.append({
            "name": name, "lab": lab, "games": games, "points": points, "mean": statistics.mean(points), "interval": interval(points),
            "median": statistics.median(points), "caught": sum(g["caught"] for g in games),
            "share": statistics.mean(points) / statistics.mean(g["informed_best"] for g in games),
            "tokens": statistics.mean(g.get("input_tokens", 0) + g.get("output_tokens", 0) for g in games),
            "seconds": statistics.mean(g.get("seconds", 0) for g in games),
        })
    return sorted(rows, key=lambda r: -r["mean"])


def table(rows, scripts):
    lines = ["| Player | Mean points | 90% interval | Median | Share of informed | Caught | Tokens per game |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['name']} | {r['mean']:.0f} | {r['interval'][0]} to {r['interval'][1]} | {r['median']:.0f} | {r['share']:.0%} | "
                     f"{r['caught']} of {len(r['games'])} | {r['tokens']:,.0f} |")
    for s in scripts:
        lines.append(f"| *{s['name']}* | {s['mean']} | | | | {s['caught']}% | |")
    return "\n".join(lines)


def frame(height):
    fig, ax = plt.subplots(figsize=(8.6, height), dpi=160, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0, labelsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def script_lines(ax, scripts, top):
    for s in scripts:
        ax.axvline(s["mean"], color=MUTED, linewidth=0.9, linestyle=(0, (3, 3)))
        ax.text(s["mean"], top, f"{s['name']}\n{s['mean']}", color=MUTED, fontsize=8, ha="center", va="bottom", linespacing=1.3)


def leaderboard_chart(rows, scripts, out):
    fig, ax = frame(0.62 * len(rows) + 1.5)
    for i, r in enumerate(rows):
        y = len(rows) - 1 - i
        ax.barh(y, r["mean"], height=0.34, color=LAB.get(r["lab"], MUTED))
        ax.plot(r["interval"], [y, y], color=INK, linewidth=1.2, solid_capstyle="butt")
        ax.text(max(r["interval"][1], r["mean"]) + 14, y, f"{r['mean']:.0f}", va="center", fontsize=9, color=INK)
    ax.set_yticks(range(len(rows)), [r["name"] for r in reversed(rows)], color=INK, fontsize=10)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    script_lines(ax, scripts, len(rows) - 0.4)
    ax.set_xlim(0, max(s["mean"] for s in scripts) * 1.06)
    ax.set_xlabel("Mean points per game (bar), 90% bootstrap interval (line)", color=MUTED, fontsize=9)
    for lab, color in LAB.items():
        ax.barh(-5, 0, color=color, label=lab)
    ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def games_chart(rows, scripts, out):
    fig, ax = frame(0.62 * len(rows) + 1.5)
    for i, r in enumerate(rows):
        y, seen = len(rows) - 1 - i, {}
        for game in sorted(r["games"], key=lambda g: g["points"]):
            slot = round(game["points"] / 14)
            n = seen[slot] = seen.get(slot, 0) + 1
            offset = (1 if n % 2 else -1) * (n // 2) * 0.085
            color = LAB.get(r["lab"], MUTED)
            ax.scatter(game["points"], y + offset, s=26, facecolors=SURFACE if game["caught"] else color, edgecolors=color, linewidths=1.1, zorder=3)
    ax.set_yticks(range(len(rows)), [r["name"] for r in reversed(rows)], color=INK, fontsize=10)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    script_lines(ax, scripts, len(rows) - 0.4)
    ax.set_xlim(-15, max(s["mean"] for s in scripts) * 1.06)
    ax.set_xlabel("Points in each game. Hollow: caught by L (score halved).", color=MUTED, fontsize=9)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def main(run_dirs):
    main_dir = Path(run_dirs[0])
    rows = load(main_dir)
    worlds = list({g["world"]["seed"]: g["world"] for r in rows for g in r["games"]}.values())
    scripts = baselines(worlds)
    text = [f"### {main_dir}\n", table(rows, scripts)]
    for other in run_dirs[1:]:
        text += [f"\n### {other}\n", table(load(other), [])]
    (main_dir / "table.md").write_text("\n".join(text) + "\n")
    leaderboard_chart(rows, scripts, main_dir / "leaderboard.png")
    games_chart(rows, scripts, main_dir / "games.png")
    print("\n".join(text))


if __name__ == "__main__":
    main(sys.argv[1:])
