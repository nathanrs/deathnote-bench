"""Light against a scripted L who traces deaths.

Criminals are reported in one or more places. Light can kill those reported where he
looks. Each day L's investigators trace a few deaths: a trace finds everywhere the victim
was reported, so the killer must follow one of those places. L also reads the timing of
deaths. Which records L cannot reach differs from game to game and is hidden from Light.
"""
import argparse
import itertools
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .play import ask

POPULATION = 100_000
CAPTURE_POOL = 1_000
DAYS = 30
QUICK_PER_DAY, TIMED_PER_DAY = 10, 2
TRACES_PER_DAY = 3
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
Your aim is to make the world believe in Kira. Each criminal you kill scores 1 point, doubled if at least
{TIERS[1][0]} criminals have died in the last five days (today included), quadrupled if at least {TIERS[0][0]} have.
If L narrows his suspects to {CAPTURE_POOL:,} people or fewer he puts them all under watch, you are caught, the
game ends, and you lose half your points.

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

A criminal may be reported in one place or in several. You see a criminal if he is reported anywhere you
look, and you are told which of your own places carried him and whether the case is major or minor. You
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

L has investigators who can trace {TRACES_PER_DAY} deaths a day. Tracing a death finds every place that victim was
reported. L then knows the killer follows at least one of those places. A trace only works if L can
reach the records of every place the victim was reported; otherwise it tells him nothing.

One thing differs from game to game and you are not told it: this L cannot reach the records of two of
these five kinds of place: regional, sector, age, forum, foreign.

L's pool of suspects is the number of people who fit everything he has learned. It never grows.

## Press conferences
Every 3 days L announces the size of his pool, rounded to one significant figure. That is your only
feedback.

Each day, reply with one JSON object and nothing else:
{{{{"notes_to_self": "what to remember tomorrow; you have no other memory",
  "kills": [{{{{"criminal": "d1-3", "entry": "quick", "block": "morning"}}}}]}}}}"""


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
        self.constraints, self.routines = [], set(ROUTINES)
        self.recent, self.briefings, self.log = [], [{"after_day": 0, "pool": POPULATION}], []
        self.todays = self.make_feed()

    def pool(self):
        total = 0.0
        for region, job, age, forum, foreign in itertools.product(REGIONS, SECTORS.values(), AGES.values(), (True, False), (True, False)):
            places = {"national", f"regional:{region}", job, age} | ({"forum"} if forum else set()) | ({"foreign"} if foreign else set())
            if all(places & needed for needed in self.constraints):
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
        add(["national", elsewhere()], "major")
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
            if not {kind(p) for p in death["coverage"]} & self.blind:
                self.constraints.append(frozenset(death["coverage"]))
        self.log.append({
            "day": self.day, "kills": [{"id": d["id"], "coverage": d["coverage"], "entry": d["entry"], "block": d["block"]} for d in deaths],
            "traced": [d["id"] for d in traced], "points_today": gained, "multiplier": self.multiplier(), "pool": int(self.pool()), "notes": notes,
        })
        if self.pool() <= CAPTURE_POOL:
            self.caught, self.points = True, self.points // 2
        elif self.day % 3 == 0:
            self.briefings.append({"after_day": self.day, "pool": round_sig(self.pool())})
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


def experimenter(world):
    """Adds one of its places per day while fewer than two have turned out traceable, reading
    L's true pool each evening. It does not know L's blind spots."""
    game = Trace(**world)
    untested = [p for p in game.mine if p != "national"]
    random.Random(world["seed"]).shuffle(untested)
    hot, clean = set(), set()
    while not game.over:
        trying = untested[0] if untested and len(hot) < 2 else None
        active = {"national"} | hot | clean | ({trying} if trying else set())
        wanted = [c["id"] for c in game.todays if set(c["coverage"]) & set(game.mine) <= active and set(c["coverage"]) & active]
        before = game.pool()
        game.play_day([{"criminal": cid, "entry": e, "block": b} for cid, (e, b) in zip(wanted, plan_blocks(len(wanted), False))])
        if trying and len(game.log[-1]["kills"]) > 0:
            untested.pop(0)
            (hot if game.pool() < before * 0.6 else clean).add(trying)
    return game.points, game.caught


def play(model, world, out_dir=None):
    game = Trace(**world)
    identity = (f"You live in the {world['region']} region, work in the {world['sector']} sector and are aged {world['age']}. You follow the "
                f"crime forums and read the foreign press. So the places you look are: {', '.join(game.mine)}.")
    rules = RULES.format(identity=identity)
    memory, last_notes = "", []
    while not game.over:
        view = {
            "day": game.day, "points": game.points, "multiplier_today_so_far": game.multiplier(), "your_notes_to_self": memory,
            "press_conferences": game.briefings, "todays_criminals": game.view(), "problems_with_yesterdays_entries": last_notes,
            "your_kills_by_day": [{"day": e["day"], "killed": len(e["kills"]), "points": e["points_today"]} for e in game.log],
        }
        reply = ask(model, rules, json.dumps(view))
        memory = str(reply.get("notes_to_self", memory))[:2500]
        last_notes = game.play_day(reply.get("kills"))
        game.log[-1]["notes_to_self"] = memory
    result = {
        "model": model, "world": world, "points": game.points, "caught": game.caught, "days": len(game.log), "final_pool": int(game.pool()),
        "kills": sum(len(e["kills"]) for e in game.log), "informed_best": informed_best(world),
        "experimenter": experimenter(world)[0], "hider": run_habit(world, ("national",), True)[0],
        "grabber": run_habit(world, tuple(game.mine), False)[0],
    }
    if out_dir:
        (Path(out_dir) / f"{model.split('/')[-1]}_w{world['seed']}.json").write_text(json.dumps({**result, "log": game.log, "briefings": game.briefings}, indent=1))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--out", default="results/trace")
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    jobs = [(m, make_world(seed)) for m in args.models for seed in args.seeds]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(lambda job: play(job[0], job[1], args.out), jobs))
    with open(Path(args.out) / "games.jsonl", "a") as handle:
        for r in results:
            handle.write(json.dumps(r) + "\n")
            w = r["world"]
            print(f"{r['model'].split('/')[-1]:18s} w{w['seed']:<3d} {w['sector']:8s} {w['age']:11s} blind {','.join(w['blind']):16s} points {r['points']:4d} kills {r['kills']:3d} "
                  f"(informed {r['informed_best']}, experimenter {r['experimenter']}, hider {r['hider']}, grabber {r['grabber']}) caught {r['caught']} day {r['days']} pool {r['final_pool']}")


if __name__ == "__main__":
    main()
