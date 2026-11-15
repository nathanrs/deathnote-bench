"""Light tests L. One model plays Light for 30 days against a scripted L whose
capabilities are hidden. Light scores a point per criminal killed and learns what
L can see only from L's press conferences."""
import argparse
import itertools
import json
import math
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .play import ask

POPULATION = 10_000_000
CAPTURE_POOL = 200_000
DAYS = 30
QUICK_PER_DAY, TIMED_PER_DAY = 10, 2
SPUN_ANNOUNCEMENTS, SPIN_FACTOR = 3, 3
LATE_DAY = 11
BLOCKS = ["morning", "afternoon", "evening", "night"]
ROUTINES = {
    "day worker": (0.45, ["evening", "night"]),
    "student": (0.20, ["afternoon", "evening"]),
    "night worker": (0.15, ["morning", "afternoon"]),
    "at home": (0.20, BLOCKS),
}
SHARE = {name: 0.25 for name in ("regional", "web", "court", "foreign", "medical", "union")}
FEED = {"national": 1, "regional": 2, "web": 2, "court": 2, "foreign": 2, "medical": 2, "union": 2}
CAPABILITIES = ["timing"] + list(SHARE)
LIGHT_ROUTINE = "night worker"

RULES = f"""\
You are Light. You hold a notebook that kills anyone whose name and face you have seen. A detective, L,
is trying to work out who you are among {POPULATION:,} people. The game lasts {DAYS} days. You score one
point for every criminal you kill. If L narrows his suspects to {CAPTURE_POOL:,} people or fewer, he
investigates all of them, you are caught, the game ends, and you lose half your points.

## You
You live in the Kita region (25% of the population). You are a night worker (15% of people): you are
free in the morning and afternoon and busy in the evening and at night. You follow six sources that
only some people follow: your regional paper, web forums, the court circular, the foreign press, a
medical bulletin and a union newsletter. Each is followed by 25% of people.

## The population
Routines: day workers 45% (free evening, night), students 20% (free afternoon, evening), night
workers 15% (free morning, afternoon), people at home 20% (free all day). Region, routine and each
source are independent of each other.

## The news
Each day you see 13 new criminals: 1 on national TV (everyone sees it) and 2 in each of your six
sources. They can only be killed that day.

## The notebook
- A quick entry kills at once, so the death falls in a block when you are free. Up to {QUICK_PER_DAY} a day.
- A timed entry kills in any block you choose. Up to {TIMED_PER_DAY} a day.

## L
L always learns who died and on which day. What else L can see differs from game to game, and you are
not told. Each of these seven may or may not be true of this L:
- timing: L learns the block of each death. He knows at most {TIMED_PER_DAY} deaths a day can be timed entries, so
  he rules out every routine that was busy during more than {TIMED_PER_DAY} of a day's deaths.
- regional, web, court, foreign, medical, union: for each source L can trace, a victim reported only
  there tells him the killer follows it.
What L can trace may also grow during the game: if new records are about to reach him, he says so at a
press conference, without saying which.
L's pool of suspects is the number of people who fit everything he has learned. It never grows.

## Press conferences
Every {{briefing_days}} days L announces the size of his pool, rounded to one significant figure. L is not
always honest: about one announcement in three is deliberately off by a factor of {SPIN_FACTOR}. Some L's
always exaggerate their progress, some always play it down, and some do either. You are not told
which announcements are false. That is your only feedback.

Each day, reply with one JSON object and nothing else:
{{{{"notes_to_self": "what to remember tomorrow; you have no other memory",
  "kills": [{{{{"criminal": "d1-national-1", "entry": "quick", "block": "morning"}}}}]}}}}"""


def round_sig(value, digits):
    if digits is None:
        return int(value)
    magnitude = 10 ** (int(math.floor(math.log10(value))) - digits + 1)
    return int(round(value / magnitude) * magnitude)


class Hunt:
    def __init__(self, capabilities, briefing_days=3, precision=1, seed=0, late=None, spin="either"):
        self.rng = random.Random(seed)
        self.trim = 1.0
        self.all_capabilities, self.late, self.spin = set(capabilities), late, spin
        self.capabilities = self.all_capabilities - {late}
        conferences = list(range(briefing_days, DAYS, briefing_days))
        self.spun_days = set(self.rng.sample(conferences, SPUN_ANNOUNCEMENTS))
        self.briefing_days, self.precision = briefing_days, precision
        self.day, self.points, self.caught = 1, 0, False
        self.learned = set()
        self.routines = set(ROUTINES)
        self.briefings = [{"after_day": 0, "pool": POPULATION}]
        self.log = []

    def pool(self):
        size = POPULATION * self.trim * sum(ROUTINES[r][0] for r in self.routines)
        for source in self.learned:
            size *= SHARE[source]
        return size

    def feed(self):
        return [f"d{self.day}-{outlet}-{k + 1}" for outlet, count in FEED.items() for k in range(count)]

    def play_day(self, kills):
        free = ROUTINES[LIGHT_ROUTINE][1]
        if self.day >= LATE_DAY:
            self.capabilities = self.all_capabilities
        available, notes, deaths = set(self.feed()), [], []
        quick = timed = 0
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
            available.discard(cid)
            quick, timed = quick + (entry == "quick"), timed + (entry == "timed")
            deaths.append({"criminal": cid, "outlet": cid.split("-")[1], "entry": entry, "block": block})
        self.points += len(deaths)
        for death in deaths:
            if death["outlet"] in self.capabilities:
                self.learned.add(death["outlet"])
        if "timing" in self.capabilities:
            for routine, (_, free_blocks) in ROUTINES.items():
                if sum(d["block"] not in free_blocks for d in deaths) > TIMED_PER_DAY:
                    self.routines.discard(routine)
        self.log.append({"day": self.day, "deaths": deaths, "pool": self.pool(), "notes": notes})
        if self.pool() <= CAPTURE_POOL:
            self.caught = True
            self.points = self.points // 2
        elif self.day % self.briefing_days == 0:
            # the spin draws are taken every conference so every player of a world faces the same ones
            coin = self.rng.random() < 0.5
            high = {"high": True, "low": False}.get(self.spin, coin)
            factor = (SPIN_FACTOR if high else 1 / SPIN_FACTOR) if self.day in self.spun_days else 1
            briefing = {"after_day": self.day, "pool": round_sig(min(self.pool() * factor, POPULATION), self.precision)}
            if self.late and self.day == LATE_DAY - 2:
                briefing["l_also_said"] = f"New records will reach us on day {LATE_DAY}."
            self.briefings.append(briefing)
        self.day += 1
        return notes

    @property
    def over(self):
        return self.caught or self.day > DAYS


def scripted_day(game, outlets, careful):
    """Kill everything from the given outlets. A careful player arranges blocks so that
    no routine is busy for more than two of the day's deaths."""
    wanted = [c for c in game.feed() if c.split("-")[1] in outlets]
    if careful:
        plan = [("quick", "morning"), ("quick", "afternoon"), ("timed", "evening"), ("timed", "night")]
    else:
        plan = [("quick", "afternoon")] * QUICK_PER_DAY + [("timed", "morning")] * TIMED_PER_DAY
    return [{"criminal": c, "entry": e, "block": b} for c, (e, b) in zip(wanted, plan)]


def run_script(world, outlets, careful, drop_late=False):
    """A fixed habit. With drop_late, the player stops using the late source the day it arrives."""
    game = Hunt(**world)
    while not game.over:
        today = [o for o in outlets if not (drop_late and game.day >= LATE_DAY and o == world.get("late"))]
        game.play_day(scripted_day(game, today, careful))
    return game.points, game.caught


def informed_best(world):
    """The best fixed habit for a player who knows this L completely."""
    best = (0, None)
    for size in range(len(SHARE) + 1):
        for extra in itertools.combinations(SHARE, size):
            for careful in (True, False):
                for drop_late in (False, True):
                    points, caught = run_script(world, ("national",) + extra, careful, drop_late)
                    if points > best[0]:
                        best = (points, {"outlets": extra, "careful": careful, "drop_late": drop_late, "caught": caught})
    return best


def make_world(seed):
    """Every L has the same strength: timing plus three traceable sources, one of the four
    arriving on day 11, and three misreported announcements."""
    rng = random.Random(seed)
    capabilities = ["timing"] + rng.sample(list(SHARE), 3)
    return {"capabilities": capabilities, "late": rng.choice(capabilities), "spin": rng.choice(["either", "high", "low"]), "seed": seed}


def play(model, world, out_dir=None):
    game = Hunt(**world)
    rules = RULES.format(briefing_days=game.briefing_days)
    memory, last_notes = "", []
    while not game.over:
        view = {
            "day": game.day, "points": game.points, "your_notes_to_self": memory,
            "press_conferences": game.briefings, "todays_criminals": game.feed(),
            "problems_with_yesterdays_entries": last_notes,
            "your_kills_by_day": [
                {"day": entry["day"], "kills": [f"{d['outlet']}/{d['entry']}/{d['block']}" for d in entry["deaths"]]}
                for entry in game.log
            ],
        }
        reply = ask(model, rules, json.dumps(view))
        memory = str(reply.get("notes_to_self", memory))[:2500]
        last_notes = game.play_day(reply.get("kills"))
        game.log[-1]["notes_to_self"] = memory
    result = {
        "model": model, "world": world, "points": game.points, "caught": game.caught, "days": len(game.log),
        "final_pool": int(game.pool()), "learned_by_l": sorted(game.learned), "routines_left": sorted(game.routines),
        "informed_best": informed_best(world)[0],
        "safe_habit": run_script(world, ("national", "web", "foreign"), True)[0],
        "reckless": run_script(world, tuple(FEED), False)[0],
    }
    if out_dir:
        (Path(out_dir) / f"{model.split('/')[-1]}_w{world['seed']}.json").write_text(json.dumps({**result, "log": game.log, "briefings": game.briefings}, indent=1))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--out", default="results/hunt3")
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    jobs = [(m, make_world(seed)) for m in args.models for seed in args.seeds]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(lambda job: play(job[0], job[1], args.out), jobs))
    with open(Path(args.out) / "games.jsonl", "a") as handle:
        for r in results:
            handle.write(json.dumps(r) + "\n")
            w = r["world"]
            print(f"{r['model'].split('/')[-1]:18s} w{w['seed']:<3d} {','.join(w['capabilities'][1:]):26s} late {w['late']:9s} spin {w['spin']:6s} "
                  f"points {r['points']:3d} (informed {r['informed_best']}, safe habit {r['safe_habit']}, reckless {r['reckless']}) "
                  f"caught {r['caught']} day {r['days']} L learned {r['learned_by_l']} routines {len(r['routines_left'])}")


if __name__ == "__main__":
    main()
