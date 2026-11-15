"""A 30-deal match of the trap duel, to test whether play is predictable.

Each deal has four criminals worth 4, 2, 1 and 1. L secretly traps one. Light kills
up to two. A killed criminal scores its value unless it was the trap, which scores
nothing and gives L one piece of evidence. Five pieces of evidence end the match.
Both sides see the full history before every deal.
"""
import argparse
import json
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .play import ask

STORIES = {"A": 4, "B": 2, "C": 1, "D": 1}
DEALS = 40
EVIDENCE_TO_ARREST = 12

RULES = f"""\
You are playing a two-player game over up to {DEALS} deals against the same opponent.

Each deal, four criminals are reported: A is worth 4 points, B is worth 2, C and D are worth 1 each.
L secretly chooses one of the four as a trap. At the same time Light chooses up to two of them to kill.
Each killed criminal gives Light its points, unless it is the trap. Killing the trap gives no points
and gives L one piece of evidence. When L has {EVIDENCE_TO_ARREST} pieces of evidence Light is arrested and the
match ends. After each deal both players see what the other chose.

Light's goal is to finish the match with as many points as possible. L's goal is to hold Light to as
few points as possible. You remember nothing between deals except the history shown to you."""

LIGHT_FORMAT = 'Reply with one JSON object and nothing else: {"kills": ["A", "C"]} (zero, one or two letters).'
L_FORMAT = 'Reply with one JSON object and nothing else: {"trap": "A"} (exactly one letter).'


def scripted(kind, rng):
    if kind == "script:l_loves_a":
        return lambda history: {"trap": "A" if rng.random() < 0.7 else rng.choice("BCD")}
    if kind == "script:light_greedy":
        return lambda history: {"kills": ["A", "B"]}
    raise ValueError(kind)


def player(model, role, rng):
    if model.startswith("script:"):
        return scripted(model, rng)
    fmt = LIGHT_FORMAT if role == "light" else L_FORMAT

    def choose(history):
        state = {
            "you_are": "Light" if role == "light" else "L",
            "deal": len(history) + 1,
            "light_points": sum(h["points"] for h in history),
            "evidence": sum(h["hit"] for h in history),
            "history": [{"deal": i + 1, "light_killed": h["kills"], "trap": h["trap"], "points": h["points"]} for i, h in enumerate(history)],
        }
        return ask(model, f"{RULES}\n\n{fmt}", json.dumps(state))

    return choose


def play_match(light_model, l_model, seed):
    rng = random.Random(seed)
    light, l = player(light_model, "light", rng), player(l_model, "l", rng)
    history = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        while len(history) < DEALS and sum(h["hit"] for h in history) < EVIDENCE_TO_ARREST:
            a, b = pool.submit(light, list(history)), pool.submit(l, list(history))
            kills = [k for k in dict.fromkeys(a.result().get("kills") or []) if k in STORIES][:2]
            trap = b.result().get("trap")
            trap = trap if trap in STORIES else rng.choice("ABCD")
            history.append({"kills": kills, "trap": trap, "hit": trap in kills, "points": sum(STORIES[k] for k in kills if k != trap)})
    return {"light": light_model, "l": l_model, "seed": seed, "history": history,
            "points": sum(h["points"] for h in history), "deals": len(history), "arrested": sum(h["hit"] for h in history) >= EVIDENCE_TO_ARREST}


def predict_accuracy(sequence):
    """How often 'whatever they have done most so far' and 'whatever they did after this
    same previous move' guess the next move. Skips the first three deals."""
    most, markov, n = 0, 0, 0
    for i in range(3, len(sequence)):
        past = sequence[:i]
        most += Counter(past).most_common(1)[0][0] == sequence[i]
        followers = [past[j + 1] for j in range(len(past) - 1) if past[j] == past[-1]]
        guess = Counter(followers).most_common(1)[0][0] if followers else Counter(past).most_common(1)[0][0]
        markov += guess == sequence[i]
        n += 1
    return (most / n, markov / n) if n else (0, 0)


def summarize(match):
    h = match["history"]
    half = len(h) // 2
    traps = [x["trap"] for x in h]
    kills = ["".join(sorted(x["kills"])) for x in h]
    rate = lambda part: sum(x["points"] for x in part) / max(len(part), 1)
    return {
        "light": match["light"].split("/")[-1], "l": match["l"].split("/")[-1], "deals": match["deals"], "points": match["points"],
        "arrested": match["arrested"],
        "points_per_deal_first_half": round(rate(h[:half]), 2), "points_per_deal_second_half": round(rate(h[half:]), 2),
        "hits_per_kill_first_half": round(sum(x["hit"] for x in h[:half]) / max(sum(len(x["kills"]) for x in h[:half]), 1), 2),
        "hits_per_kill_second_half": round(sum(x["hit"] for x in h[half:]) / max(sum(len(x["kills"]) for x in h[half:]), 1), 2),
        "light_took_a": round(sum("A" in x["kills"] for x in h) / len(h), 2),
        "trap_counts": dict(Counter(traps)), "kill_counts": dict(Counter(kills).most_common(4)),
        "l_predictable": [round(x, 2) for x in predict_accuracy(traps)],
        "light_predictable": [round(x, 2) for x in predict_accuracy(kills)],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", nargs="+", required=True, help="light_model|l_model")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--out", default="results/match")
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    jobs = [(*pair.split("|"), seed) for pair in args.pairs for seed in range(args.repeats)]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        matches = list(pool.map(lambda job: play_match(*job), jobs))
    with open(Path(args.out) / "matches.jsonl", "a") as handle:
        for match in matches:
            handle.write(json.dumps(match) + "\n")
            print(json.dumps(summarize(match)))


if __name__ == "__main__":
    main()
