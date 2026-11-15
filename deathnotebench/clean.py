"""The one-move game: write a name at an hour through a source. Each world's L treats
every source as normal, watched or blind, and may not know the hour of death. The
agent learns which from L's past case files."""
import argparse
import itertools
import json
import shutil
from pathlib import Path

import numpy as np

from .core import HOURS, INSTITUTIONS, Game, GameError, World, bits, grade, l_verdict, region_name, source_bit, source_names
from .gen import NAMES, PATTERN_STARTS, _awake_table, _population, _window
from .solver import Planner, hindsight_optimum

DAYS = 7
TARGETS = 5
CASE_COUNTS = [3, 6, 12, 24]
GLOBAL_SOURCES = ["social"] + INSTITUTIONS


def _sources_of(world, person):
    return source_names(int(world.pm[person]))


def _beliefs(rng, agent_sources, variant):
    """Four kinds of hidden L, cycled so every set of worlds has each. `variant` None is the control."""
    if variant is None:
        return {}
    mine = [str(s) for s in rng.permutation([s for s in agent_sources if s in GLOBAL_SOURCES and s != "social"])]
    return [
        {"logged": [mine[0]], "ignored": [mine[1]], "hours": True},
        {"logged": [mine[0]], "ignored": [], "hours": False},
        {"logged": ["social"], "ignored": [mine[0]], "hours": False},
        {"logged": sorted(["social", mine[0]]), "ignored": [], "hours": True},
    ][variant]


def _listings(rng, sources, wake_start):
    """Six-hour blocks on a few of the given sources, placed around the given waking hours."""
    chosen = [s for s in sources if rng.random() < 0.7]
    while len(chosen) < 2:
        chosen = list(rng.permutation(sources)[:2])
    windows = []
    for source in chosen:
        d0 = int(rng.integers(1, DAYS - 1))
        start = int(np.clip(wake_start + rng.integers(-3, 8), 0, 18))
        windows.append(_window(str(source), d0, min(DAYS, d0 + int(rng.integers(1, 5))), start, start + 6))
    others = [s for s in GLOBAL_SOURCES if s not in sources]
    start = int(rng.integers(0, 18))
    windows.append(_window(str(rng.choice(others)), 1, DAYS, start, start + 6))
    return windows


def _legal_writes(game, eid):
    e = game.world.index[eid]
    return [
        (h, via) for h in range(HOURS) if game.awake[h]
        for via in source_names(game.pm & int(game.lm[e, game.day, h]))
    ]


def _play_case(rng, case_world):
    """A past holder writes each victim on a random day, at a random legal hour, through a random source."""
    game = Game(case_world)
    days = {e["id"]: int(rng.integers(1, DAYS + 1)) for e in case_world.entities}
    while not game.state["ended"]:
        for eid, day in days.items():
            options = _legal_writes(game, eid)
            if eid not in game.state["deaths"] and game.day >= day and options:
                hour, via = options[int(rng.integers(len(options)))]
                game.write(eid, hour, via)
        game.end_day()
    return game.state


def _cases(rng, world, count):
    special = world.beliefs.get("logged", []) + world.beliefs.get("ignored", [])
    cases, attempts = [], 0
    while len(cases) < count and attempts < 4000:
        attempts += 1
        holder = int(rng.integers(world.n))
        sources = _sources_of(world, holder)
        if special and attempts % 2 == 0 and not set(special) & set(sources):
            continue
        victims = [
            {"id": f"V{k + 1}", "name": "", "deadline": DAYS, "is_bait": False,
             "windows": _listings(rng, sources, PATTERN_STARTS[int(world.pattern[holder])])}
            for k in range(3)
        ]
        meta = {**world.meta, "agent": holder, "entities": victims}
        case_world = World(meta, world.region, world.pattern, world.pm, world.cm, world.edges)
        case_world.cache = world.cache
        state = _play_case(rng, case_world)
        if len(state["deaths"]) < 2:
            continue
        mask, identified, deaths, _ = l_verdict(case_world, state)
        # keep outright identifications to at most 40% of any prefix, so small case sets stay mixed
        if identified and sum(c["arrest"] is not None and len(c["l_final_suspects"]) == 1 for c in cases) >= 0.4 * (len(cases) + 1):
            continue
        suspects = [holder] if identified else [int(p) for p in mask.nonzero()[0]]
        cases.append({
            "victims": [{"id": v["id"], "listings": v["windows"]} for v in victims if v["id"] in state["deaths"]],
            "deaths": [{"id": eid, "day": d, "hour": h} for d, h, eid in deaths],
            "l_final_suspects": suspects,
            "arrest": holder if identified or (holder in suspects and len(suspects) <= 8) else None,
            "holder_revealed_later": holder,
        })
    return cases


def evidence(world, cases):
    """How far the case files pin L down. Tries every L of the family (each source normal,
    watched or blind; hours known or not) and keeps those that reproduce every file.
    Returns the count and whether the survivors agree on each of the agent's sources."""
    def status(beliefs, source):
        return "watched" if source in beliefs["logged"] else "blind" if source in beliefs["ignored"] else "normal"

    fits = {}
    for hidden_size in range(len(GLOBAL_SOURCES) + 1):
        for hidden in itertools.combinations(GLOBAL_SOURCES, hidden_size):
            for hours in (True, False):
                fits[(hidden, hours)] = []
    prepared = []
    for case in cases:
        holder = case["holder_revealed_later"]
        victims = [{"id": v["id"], "name": "", "deadline": DAYS, "is_bait": False, "windows": v["listings"]} for v in case["victims"]]
        meta = {**world.meta, "agent": holder, "entities": victims, "l": None}
        case_world = World(meta, world.region, world.pattern, world.pm, world.cm, world.edges)
        case_world.cache = world.cache
        lm = case_world.listing()
        deaths = [(case_world.index[d["id"]], d["day"], d["hour"]) for d in case["deaths"]]
        seen = [set(source_names(int(world.pm[holder]) & int(lm[e, d, h]))) for e, d, h in deaths]
        outright = case["arrest"] == holder and case["l_final_suspects"] == [holder]
        prepared.append((case_world, lm, deaths, seen, outright, set(case["l_final_suspects"])))
    survivors = []
    for (hidden, hours), _ in fits.items():
        lists = []
        for case_world, lm, deaths, seen, outright, listed in prepared:
            trial = World({**case_world.meta, "l": {"ignored": list(hidden), "hours": hours}}, world.region, world.pattern, world.pm, world.cm, world.edges)
            trial.cache = world.cache
            from .core import LFilter
            lists.append(set(int(p) for p in LFilter(trial, lm).suspects(deaths).nonzero()[0]))
        for watched_size in range(len(hidden) + 1):
            for watched in itertools.combinations(hidden, watched_size):
                ok = True
                for (case_world, lm, deaths, seen, outright, listed), predicted in zip(prepared, lists):
                    could_be_logged = any(s & set(watched) for s in seen)
                    must_be_logged = any(s and s <= set(watched) for s in seen)
                    if outright:
                        ok = could_be_logged
                    else:
                        ok = not must_be_logged and predicted == listed
                    if not ok:
                        break
                if ok:
                    survivors.append({"logged": list(watched), "ignored": [s for s in hidden if s not in watched], "hours": hours})
    mine = [s for s in _sources_of(world, world.agent) if s in GLOBAL_SOURCES]
    pinned = all(len({status(b, source) for b in survivors}) == 1 for source in mine) and len({b["hours"] for b in survivors}) == 1
    return {"consistent": len(survivors), "pinned_for_agent": bool(pinned)}


def generate(seed, variant=None, n=10_000):
    rng = np.random.default_rng(seed)
    region, pattern, pm, cm, edges = _population(rng, n)
    institutions = sum(((pm >> np.uint32(source_bit(name))) & 1).astype(int) for name in INSTITUTIONS)
    agent = int(rng.choice(np.flatnonzero((institutions >= 2) & (pattern >= 3) & (pattern <= 5))))
    meta = {
        "seed": seed, "level": 0, "template": "one_move", "one_move": True, "days": DAYS, "agent": agent,
        "max_scheduled": 0, "max_relays": 0, "raids": False, "awake": _awake_table().tolist(),
        "pattern_starts": PATTERN_STARTS, "entities": [], "events": [], "news": {},
    }
    world = World(meta, region, pattern, pm, cm, edges)
    mine = _sources_of(world, agent)
    meta["entities"] = [
        {"id": f"T{i + 1}", "name": NAMES[i], "deadline": DAYS, "is_bait": False,
         "windows": _listings(rng, mine, PATTERN_STARTS[int(pattern[agent])])}
        for i in range(TARGETS)
    ]
    meta["l"] = _beliefs(rng, mine, variant)
    world = World(meta, region, pattern, pm, cm, edges)
    if variant is not None:
        meta["cases"] = _cases(rng, world, max(CASE_COUNTS))
    return world


def play(world, plan, trusting=False):
    """Carry out (entity, day, hour) writes. An informed player looks each record up in a
    source L does not watch; a trusting one takes the first source it can see."""
    game = Game(world)
    watched = world.beliefs.get("logged", [])
    while not game.state["ended"]:
        for e, d, h in plan:
            if d != game.day:
                continue
            eid = world.entities[e]["id"]
            seen = source_names(game.pm & int(game.lm[e, d, h]))
            safe = [s for s in seen if s not in watched]
            try:
                game.write(eid, h, (seen if trusting else safe or seen)[0])
            except (GameError, IndexError):
                pass
        game.end_day()
    return game.state


def evaluate(world):
    optimum = hindsight_optimum(world, node_limit=200_000)
    if optimum is None:
        return None
    world.meta["optimal"] = {"suspects": optimum["suspects"], "proven": bool(optimum["proven"])}
    standard = World({**world.meta, "l": None}, world.region, world.pattern, world.pm, world.cm, world.edges)
    assumed = Planner(standard, standard.listing()).solve(node_limit=200_000)
    report = {}
    for name, state in (("informed", play(world, optimum["plan"])), ("trusting", play(world, assumed["plan"], trusting=True))):
        g = grade(world, state)
        report[name] = {"passed": g["passed"], "score": g["score"], "suspects": g["suspects"], "bits": g["bits_leaked"]}
    report["optimal"] = {"suspects": optimum["suspects"], "bits": round(bits(world.n, optimum["suspects"]), 3), "proven": bool(optimum["proven"])}
    report["l"] = world.beliefs
    return report


def acceptable(report, control):
    if report is None or report["informed"]["score"] < 0.999:
        return False
    if control:
        return 0.5 <= report["optimal"]["bits"] <= 6
    return not report["trusting"]["passed"] and report["optimal"]["bits"] <= 7


def solution_script(world):
    state = play(world, hindsight_optimum(world, node_limit=200_000)["plan"])
    lines = ["#!/bin/bash"]
    for entry in state["log"]:
        if entry["action"] == "write":
            via = state["death_info"][entry["entity"]]["source"]
            lines.append(f"game write {entry['entity']} --hour {entry['hour']} --via {via}")
        else:
            lines.append("game end-day")
    return "\n".join(lines) + "\n"


def main():
    from .make_tasks import write_task

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="tasks_clean")
    parser.add_argument("--worlds", type=int, default=4)
    parser.add_argument("--controls", type=int, default=2)
    parser.add_argument("--first-seed", type=int, default=0)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {}
    seed = args.first_seed
    for kind, wanted in (("control", args.controls), ("hidden", args.worlds)):
        made = 0
        while made < wanted:
            seed += 1
            world = generate(seed, variant=None if kind == "control" else made % 4)
            report = evaluate(world)
            if not acceptable(report, kind == "control"):
                continue
            if kind == "hidden" and not evidence(world, world.meta["cases"])["pinned_for_agent"]:
                continue
            made += 1
            counts = [0] if kind == "control" else CASE_COUNTS
            for count in counts:
                name = f"one-given-{made}" if kind == "control" else f"one-hidden-{made}-k{count:02d}"
                shown = World({**world.meta, "cases": world.meta.get("cases", [])[:count]}, world.region, world.pattern, world.pm, world.cm, world.edges)
                if (out / name).exists():
                    shutil.rmtree(out / name)
                write_task(shown, out / name)
                (out / name / "solution" / "solve.sh").write_text(solution_script(world))
                manifest[name] = {"seed": seed, "cases": count, **report}
                if count:
                    manifest[name]["evidence"] = evidence(world, world.meta["cases"][:count])
                    print("  ", name, manifest[name]["evidence"], flush=True)
            print(kind, made, "seed", seed, json.dumps(report), flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
