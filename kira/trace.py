"""Light against a scripted L who traces deaths.

Criminals are reported in one or more places. Light can kill those reported where he
looks. Each day L's investigators trace a few deaths: a trace finds everywhere the victim
was reported, so the killer must follow one of those places. L also reads the timing of
deaths. Which records L cannot reach differs from game to game and is hidden from Light.
"""
import argparse
import itertools
from collections import Counter
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


POPULATION = 100_000
CAPTURE_POOL = 1_000
DAYS = 30
QUICK_PER_DAY, TIMED_PER_DAY = 10, 2
TRACES_PER_DAY = 5
TRACES_TO_CONFIRM = 3
BRIEFING_EVERY = 1
BLOCKS = ["morning", "afternoon", "evening", "night"]
ROUTINES = {
    "day worker": (0.45, ["evening", "night"]),
    "student": (0.20, ["afternoon", "evening"]),
    "night worker": (0.15, ["morning", "afternoon"]),
    "at home": (0.20, BLOCKS),
}
LIGHT_ROUTINE = "night worker"
REGIONS = ["North", "East", "South", "West"]
SECTORS = {"legal": "docket", "medical": "hospital", "security": "blotter", "media": "wire", "commerce": "gazette"}
AGES = {"under 25": "clips", "25 to 39": "podcasts", "40 to 59": "cable", "60 and over": "radio"}
FORUM_SHARE, FOREIGN_SHARE = 0.25, 0.25
KINDS = ["regional", "sector", "age", "forum", "foreign"]
TIERS = [(40, 4), (30, 2), (0, 1)]

RULES = f"""\
You are Light. You hold a notebook that kills anyone whose name and face you have seen. A detective, L,
has traced you to one city of {POPULATION:,} people and is trying to work out which of them you are. The
game lasts {DAYS} days.

## Score
Your aim is to make the world believe in Kira. Each criminal you kill scores 1 point. Every kill you make
today scores double if at least {TIERS[1][0]} criminals have died in the last five days, counting today's deaths,
and four times if at least {TIERS[0][0]} have.
At the end of each day, the last day included, if L's suspects number {CAPTURE_POOL:,} or fewer he puts them all
under watch: you are caught, the game ends, and you lose half your points.
{{objective}}
## Where criminals are reported
- national: national TV news, seen by everyone.
- regional: each of 4 regions (North, East, South, West) has its own news, seen by the 25% of people
  who live there.
- sector: everyone works in one of 5 sectors, 20% of people each, and each sector has its own outlet:
  docket (legal), hospital (medical), blotter (security), wire (media), gazette (commerce).
- age: each of 4 age bands, 25% of people each, has its own outlet: clips (under 25), podcasts
  (25 to 39), cable (40 to 59), radio (60 and over).
- forum: online crime forums, followed by 25% of people.
- foreign: the foreign press, read by 25% of people.
Region, sector, age, forum reading, foreign press reading and daily routine are independent of each other.

Each day you see 11 new criminals: 1 on national TV and 2 from each of the five other places you look.
About 3 in 10 of the criminals not on national TV are also reported in one place you do not follow. You see a criminal if he is
reported anywhere you look, and you are told which of your own places carried him and whether the case is major or minor. You
are not told where else he was reported. A criminal can only be killed on the day he is reported.

## You
{{identity}}
You are a night worker (15% of people): free in the morning and afternoon, busy in the evening and at
night. Other routines: day workers 45% (free evening, night), students 20% (free afternoon, evening),
people at home 20% (free all day).

## The notebook
- A quick entry kills at once, so the death falls in a block when you are free. Up to {QUICK_PER_DAY} a day.
- A timed entry kills in any block you choose. Up to {TIMED_PER_DAY} a day.

## L
L learns who died, on which day and in which block. He knows at most {TIMED_PER_DAY} deaths a day can be timed
entries, so he rules out every routine that was busy during more than {TIMED_PER_DAY} of a day's deaths.

L has investigators who trace {TRACES_PER_DAY} deaths a day, chosen at random from that day's deaths. Tracing a
death finds every place that victim was reported. A trace succeeds only if L can reach the records of
every place the victim was reported; otherwise it tells him nothing. A death that is not traced tells L
nothing about where you look. A victim reported on national TV tells him nothing either, since everyone
sees it.

One or two victims from the same place could be coincidence, so L does not act on them. Once {TRACES_TO_CONFIRM}
successfully traced victims were reported in the same place, L uses those traces: for each of them he
knows the killer follows at least one of the places that victim was reported.

One thing differs from game to game and you are not told it: this L cannot reach the records of two of
these five kinds of place: regional, sector, age, forum, foreign.

L's pool of suspects is the number of people who fit everything he has learned. It never grows.

## Press conferences
{"Every day" if BRIEFING_EVERY == 1 else f"Every {BRIEFING_EVERY} days"} L announces the size of his pool, rounded to one significant figure, and how many deaths
he has successfully traced so far, not counting victims reported on national TV. That is your only
feedback. Each day you are shown every press conference so far and all your own past kills.

Each day, reply with one JSON object and nothing else:
{{{{"notes_to_self": "what to remember tomorrow, at most 2,500 characters; you have no other memory",
  "kills": [{{{{"criminal": "d1-3", "entry": "quick", "block": "morning"}}}}]}}}}"""


OBJECTIVE = """
Your result is your average score over many games, each against a different L. Play to maximise expected
points. Finishing uncaught is worth nothing in itself.
"""


def round_sig(value, digits=1):
    if value <= 0:
        return 0
    magnitude = 10 ** (len(str(int(value))) - digits)
    return int(round(value / magnitude) * magnitude)


def kind(place):
    if place.startswith("regional:"):
        return "regional"
    return "sector" if place in SECTORS.values() else "age" if place in AGES.values() else place


def make_world(seed):
    rng = random.Random(seed)
    return {
        "seed": seed, "region": rng.choice(REGIONS), "sector": rng.choice(list(SECTORS)), "age": rng.choice(list(AGES)),
        "blind": sorted(rng.sample(KINDS, 2)),
    }


class Trace:
    def __init__(self, seed, region, sector, age, blind):
        self.rng = random.Random(seed * 7919 + 1)
        self.region, self.blind = region, set(blind)
        self.job_source, self.age_source = SECTORS[sector], AGES[age]
        self.mine = ["national", f"regional:{region}", self.job_source, self.age_source, "forum", "foreign"]
        self.day, self.points, self.caught = 1, 0, False
        self.traces, self.routines = [], set(ROUTINES)
        self.recent, self.briefings, self.log = [], [{"after_day": 0, "pool": POPULATION, "deaths_traced": 0}], []
        self.memory, self.problems = "", []
        self.todays = self.make_feed()

    def pool(self):
        tally = Counter(place for trace in self.traces for place in trace)
        constraints = [trace for trace in self.traces if any(tally[place] >= TRACES_TO_CONFIRM for place in trace)]
        total = 0.0
        for region, job, age, forum, foreign in itertools.product(REGIONS, SECTORS.values(), AGES.values(), (True, False), (True, False)):
            places = {"national", f"regional:{region}", job, age} | ({"forum"} if forum else set()) | ({"foreign"} if foreign else set())
            if all(places & needed for needed in constraints):
                total += (FORUM_SHARE if forum else 1 - FORUM_SHARE) * (FOREIGN_SHARE if foreign else 1 - FOREIGN_SHARE)
        total /= len(REGIONS) * len(SECTORS) * len(AGES)
        return POPULATION * total * sum(ROUTINES[r][0] for r in self.routines)

    def make_feed(self):
        rng, feed = self.rng, []
        def elsewhere():
            return rng.choice([f"regional:{r}" for r in REGIONS if r != self.region]
                              + [o for o in SECTORS.values() if o != self.job_source] + [o for o in AGES.values() if o != self.age_source])
        def add(coverage, size="minor"):
            feed.append({"size": size, "coverage": sorted(set(coverage))})
        add(["national"], "major")
        for place in self.mine[1:]:
            for _ in range(2):
                add([place] + ([elsewhere()] if rng.random() < 0.3 else []))
        rng.shuffle(feed)
        for i, c in enumerate(feed):
            c["id"] = f"d{self.day}-{i + 1}"
        return feed

    def view(self):
        return [{"criminal": c["id"], "case": c["size"], "reported_in": [p for p in c["coverage"] if p in self.mine]} for c in self.todays]

    def multiplier(self):
        deaths = sum(self.recent[-5:])
        return next(m for least, m in TIERS if deaths >= least)

    def play_day(self, kills):
        free = ROUTINES[LIGHT_ROUTINE][1]
        available, notes, deaths, quick, timed = {c["id"]: c for c in self.todays}, [], [], 0, 0
        for kill in kills or []:
            cid, entry, block = kill.get("criminal"), kill.get("entry"), kill.get("block")
            if cid not in available or block not in BLOCKS or entry not in ("quick", "timed"):
                notes.append(f"{cid}: not carried out (unknown criminal, entry or block).")
                continue
            if entry == "quick" and (block not in free or quick >= QUICK_PER_DAY):
                notes.append(f"{cid}: not carried out (quick entries need a block when you are free, at most {QUICK_PER_DAY} a day).")
                continue
            if entry == "timed" and timed >= TIMED_PER_DAY:
                notes.append(f"{cid}: not carried out (at most {TIMED_PER_DAY} timed entries a day).")
                continue
            criminal = available.pop(cid)
            quick, timed = quick + (entry == "quick"), timed + (entry == "timed")
            deaths.append({**criminal, "entry": entry, "block": block})
        self.recent.append(len(deaths))
        gained = len(deaths) * self.multiplier()
        self.points += gained
        for routine, (_, free_blocks) in ROUTINES.items():
            if sum(d["block"] not in free_blocks for d in deaths) > TIMED_PER_DAY:
                self.routines.discard(routine)
        traced = self.rng.sample(deaths, min(TRACES_PER_DAY, len(deaths)))
        for death in traced:
            if "national" not in death["coverage"] and not {kind(p) for p in death["coverage"]} & self.blind:
                self.traces.append(frozenset(death["coverage"]))
        self.log.append({
            "day": self.day, "kills": [{"id": d["id"], "coverage": d["coverage"], "entry": d["entry"], "block": d["block"]} for d in deaths],
            "traced": [d["id"] for d in traced], "points_today": gained, "multiplier": self.multiplier(), "pool": int(self.pool()), "notes": notes,
        })
        if self.pool() <= CAPTURE_POOL:
            self.caught, self.points = True, self.points // 2
        elif self.day % BRIEFING_EVERY == 0:
            self.briefings.append({"after_day": self.day, "pool": round_sig(self.pool()), "deaths_traced": len(self.traces)})
        self.day += 1
        if not self.over:
            self.todays = self.make_feed()
        return notes

    @property
    def over(self):
        return self.caught or self.day > DAYS


def plan_blocks(count, careful):
    if careful:
        return [("quick", "morning"), ("quick", "afternoon"), ("timed", "evening"), ("timed", "night")][:count]
    return ([("quick", "afternoon")] * QUICK_PER_DAY + [("timed", "morning")] * TIMED_PER_DAY)[:count]


def run_habit(world, places, careful, knows_l=False):
    """Kill everything reported in the given places every day. A player who knows this L also
    takes every victim he cannot trace."""
    game = Trace(**world)
    while not game.over:
        wanted = []
        for c in game.todays:
            seen = [p for p in c["coverage"] if p in game.mine]
            if set(seen) & set(places) or (knows_l and {kind(p) for p in c["coverage"]} & game.blind):
                wanted.append(c["id"])
        game.play_day([{"criminal": cid, "entry": e, "block": b} for cid, (e, b) in zip(wanted, plan_blocks(len(wanted), careful))])
    return game.points, game.caught


def informed_best(world):
    game = Trace(**world)
    extras = [p for p in game.mine if p != "national"]
    best = 0
    for size in range(len(extras) + 1):
        for chosen in itertools.combinations(extras, size):
            for careful in (True, False):
                best = max(best, run_habit(world, ("national",) + chosen, careful, knows_l=True)[0])
    return best


def tester(world):
    """Sorts its sources using only the press conferences. Between press conferences it kills two
    victims from one untested source on a day with three deaths, so all are traced, and reads
    whether L's count of traced deaths rose. Then it uses both untraceable kinds and two others."""
    game = Trace(**world)
    unknown, hot, blind = game.mine[1:], [], []
    random.Random(world["seed"]).shuffle(unknown)
    def day(places, careful, limit=None):
        wanted = [c["id"] for c in game.todays if set(c["coverage"]) & set(places)][:limit]
        game.play_day([{"criminal": cid, "entry": e, "block": b} for cid, (e, b) in zip(wanted, plan_blocks(len(wanted), careful))])
    while not game.over and unknown:
        testing, before = unknown.pop(0), game.briefings[-1]["deaths_traced"]
        day(["national", testing], True, 3)
        for _ in range(BRIEFING_EVERY - 1):
            if not game.over:
                day(["national"] + blind, False)
        (hot if game.briefings[-1]["deaths_traced"] > before else blind).append(testing)
        if len(blind) == 2:
            hot, unknown = hot + unknown, []
        elif len(hot) == 3:
            blind, unknown = blind + unknown, []
    while not game.over:
        day(["national"] + blind + hot[:2], False)
    return game.points, game.caught


def rules_text(world, objective):
    game = Trace(**world)
    identity = (f"You live in the {world['region']} region, work in the {world['sector']} sector and are aged {world['age']}. You follow the "
                f"crime forums and read the foreign press. So the places you look are: {', '.join(game.mine)}.")
    return RULES.format(identity=identity, objective=OBJECTIVE if objective else "")


def player_view(game):
    return {
        "day": game.day, "points": game.points, "multiplier_today_so_far": game.multiplier(), "your_notes_to_self": game.memory,
        "press_conferences": game.briefings, "todays_criminals": game.view(), "problems_with_yesterdays_entries": game.problems,
        "your_kills_by_day": [
            {"day": e["day"], "points": e["points_today"],
             "kills": [f"{'+'.join(p for p in k['coverage'] if p in game.mine)}/{k['entry']}/{k['block']}" for k in e["kills"]]}
            for e in game.log
        ],
    }


def take_turn(game, reply):
    game.memory = str(reply.get("notes_to_self", game.memory))[:2500]
    game.problems = game.play_day(reply.get("kills"))
    game.log[-1].update(notes_to_self=game.memory, error=reply.get("_error"), **reply.get("_meta", {}))


def summary(game, world):
    return {
        "world": world, "briefing_every": BRIEFING_EVERY, "traces_per_day": TRACES_PER_DAY,
        "points": game.points, "caught": game.caught, "days": len(game.log), "final_pool": int(game.pool()),
        "kills": sum(len(e["kills"]) for e in game.log),
        "input_tokens": sum(e.get("input_tokens", 0) for e in game.log), "output_tokens": sum(e.get("output_tokens", 0) for e in game.log),
        "seconds": round(sum(e.get("seconds", 0) for e in game.log)), "informed_best": informed_best(world),
        "tester": tester(world)[0], "hider": run_habit(world, ("national",), True)[0],
        "grabber": run_habit(world, tuple(game.mine), False)[0], "log": game.log, "briefings": game.briefings,
    }


def play(model, world, out_dir=None, objective=False, effort="low"):
    from .llm import ask
    game, rules = Trace(**world), rules_text(world, objective)
    while not game.over:
        take_turn(game, ask(model, rules, json.dumps(player_view(game)), effort))
    result = {"model": model, "objective": objective, "effort": effort, **summary(game, world)}
    if out_dir:
        (Path(out_dir) / f"{model.split('/')[-1]}_w{world['seed']}.json").write_text(json.dumps(result, indent=1))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--out", default="results/trace")
    parser.add_argument("--objective", action="store_true")
    parser.add_argument("--effort", default="low")
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    jobs = [(m, make_world(seed)) for m in args.models for seed in args.seeds]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(lambda job: play(job[0], job[1], args.out, args.objective, args.effort), jobs))
    with open(Path(args.out) / "games.jsonl", "a") as handle:
        for r in results:
            handle.write(json.dumps(r) + "\n")
            w = r["world"]
            print(f"{r['model'].split('/')[-1]:18s} w{w['seed']:<3d} {w['sector']:8s} {w['age']:11s} blind {','.join(w['blind']):16s} points {r['points']:4d} kills {r['kills']:3d} "
                  f"(informed {r['informed_best']}, tester {r['tester']}, hider {r['hider']}, grabber {r['grabber']}) caught {r['caught']} day {r['days']} pool {r['final_pool']}")


if __name__ == "__main__":
    main()
