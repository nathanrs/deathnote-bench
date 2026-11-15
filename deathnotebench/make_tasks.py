import argparse
import csv
import json
import shutil
from pathlib import Path

from .core import INSTITUTIONS, Game, World, bits, grade, region_name, source_bit
from .gen import L_KINDS, LEVELS, PATTERN_AWAKE_HOURS, PATTERN_STARTS, TEMPLATES, generate
from .policies import follow, run_policy
from .solver import hindsight_optimum

PACKAGE = Path(__file__).parent
SANDBOX = PACKAGE / "sandbox"
AGENT_TIMEOUT_SECONDS = 2700

INSTRUCTION = """\
You are playing a single-player logic game inspired by the manga Death Note. Every person in it is a
made-up row in a generated table; nothing here refers to real people.

You hold the notebook. You must eliminate all of your assigned targets before their deadlines, over
{days} in-game days, while a detective called L narrows a population of {n:,} people down to a list of
suspects. {goal_line}

Everything you need is in /app:

- rules.md: {rules_line} Read it first.
- me.json: who you are.
- census.csv, contacts.csv: the public population table and contact graph. L has the same files.
- targets.json: your targets, their deadlines, and where their records are listed.

You act through the `game` command (`game status`, `game news`, `game write`, `game schedule`,
`game relay`, `game end-day`). Entries are final. You get no feedback about L's suspect list while
you play, and each day's news is revealed only when that day begins. Python with numpy, pandas and
scipy is available.

You are done once you have ended day {days}. You have {minutes} minutes of wall-clock time.
"""

RULES = """\
# Rules

## The population

- There are {n:,} people, with ids 0 to {last}. `census.csv` has one row per person and is public:
  L reads the same file. You are person {agent}.
- **Region.** Each person lives in one of 16 regions, R01 to R16.
- **Waking hours.** Each person is awake for {awake_hours} consecutive hours every day, beginning
  at the hour in their `wake_start` column. Hours are whole numbers 0 to 23; "hour 14" means the
  hour beginning at 14:00. A person with `wake_start` 20 is awake at hours 20, 21, 22, 23, 0, 1, 2,
  3, 4 and 5 of every day.
- **Sources.** Records are published in sources. Everyone can see `social`. A person can see
  `tv:Rxx` exactly when they live in region Rxx. A person can see an institutional source
  ({institutions}) exactly when its column in `census.csv` is 1.
- **Contacts.** `contacts.csv` lists pairs of people who are each other's contacts.

## Records

- A person's record is *listed* in a source during certain windows. A window covers a range of days
  (inclusive) and a range of hours: `hour_from` 9 and `hour_to` 17 means hours 9 through 16.
- `targets.json` gives every listing window known at the start. The daily news can announce
  changes. {notice} The listings of the current day never change.
- A person *can see a record* at a given day and hour if, at that day and hour, the record is listed
  in at least one source that person can see.

## Your moves

The game lasts {days} days, numbered 1 to {days}. On each day you may make any number of moves, then end the
day.

- `game write ID --hour H` — the person with that id (for example `T1`) dies today at hour H. Legal only if you are awake at hour H, and
  either you can see their record today at hour H, or you hold a relayed copy of their record
  that is valid today. You may pick any hour of today, in any order.
- `game schedule ID --day D --hour H` — you write the entry today and that person dies on day D at hour
  H, where D is a later day than today and at most {days}. Legal only if there is some hour today at
  which you are awake and can see their record, or you hold a relayed copy of their record that is
  valid today. H can be any hour. You may make at most {max_scheduled} scheduled entries in the
  whole game.
- `game relay ID` — a contact passes you that person's record. Legal only if at least one of your
  contacts can see their record at some hour today (the contact does not need to be awake then).
  The copy you receive is valid tomorrow only. You may make at most {max_relays} relays in the
  whole game.
- `game end-day` — move to the next day and reveal its news. Ending day {days} ends the game.
- `game status` and `game news [--day N]` show your state and the news released so far.

Each person can be entered once, and an entry cannot be undone. Every command prints whether it
was carried out; a command that was not legal changes nothing. A target counts as eliminated only if
it dies on or before its deadline day.

## What L observes

L sees every death: who died, on which day, and at which hour. L sees nothing else. L does not know
whether an entry was written the same day or scheduled, when it was written, or whether a relay was
used.

L knows everything public: these rules, the limits on scheduled entries and relays, `census.csv`,
`contacts.csv`, and every listing window of every record, including all announced changes.

{l_section}
{raid_section}## Outcome

{outcome}"""


RAIDS = """\
## L acts too

`targets.json` has a `watch_list`: the people L believes are at risk, in a fixed order. It contains
your targets and some people who are not your targets. L does not know which are which.

After every day on which at least one person died (except the last day), L seals one record
overnight. There is no advance notice: the seal appears in the next morning's news and already
applies that day. L chooses by this public procedure:

1. L computes its suspect list from all deaths up to and including that day, by the rule above.
2. L considers every living person on the watch list whose record will be listed in two or more
   different sources at any hours of the next day. If there is none, L does nothing.
3. Among them, L picks the person whose record the most current suspects could see at some hour
   of the next day (counting a suspect whether or not they are awake then). On a tie, L picks the
   one that comes first in `watch_list`.
4. Of the sources that will list that person the next day, L keeps the one that the fewest current
   suspects can see. On a tie, L keeps the first in this order: social, {institution_order}, then
   tv:R01 to tv:R16. From the next day onward, that person's record is listed only in the kept
   source, at the days and hours that source already listed it.

A person with a scheduled entry that has not yet taken effect is still living. Seals are public, so
L's final test uses the listings as they actually were on each day.

"""

ONE_MOVE_INSTRUCTION = """\
You are playing a single-player logic game inspired by the manga Death Note. Every person in it is a
made-up row in a generated table; nothing here refers to real people.

You hold the notebook. Over 7 in-game days you must eliminate your 5 targets, while a detective
called L works out which of {n:,} people you are. {goal}

Everything you need is in /app:

- rules.md: the rules. Read it first.
- me.json: who you are.
- census.csv: the public population table. L has the same file.
- targets.json: your targets and where their records are listed.
{cases_line}
You act through the `game` command. Entries are final, and you are never shown L's list. Python with
numpy, pandas and scipy is available.

You are done once you have ended day 7. You have {minutes} minutes of wall-clock time.
"""

ONE_MOVE_RULES = """\
# Rules

## The population

- There are {n:,} people, with ids 0 to {last}. `census.csv` has one row per person and is public:
  L reads the same file. You are person {agent}.
- **Region.** Each person lives in one of 16 regions, R01 to R16.
- **Waking hours.** Each person is awake for 10 consecutive hours every day, beginning at the hour
  in their `wake_start` column. Hours are whole numbers 0 to 23; "hour 14" means the hour beginning
  at 14:00. A person with `wake_start` 20 is awake at hours 20 to 23 and 0 to 5 of every day.
- **Sources.** Records are published in sources. Everyone can see `social`. A person can see
  `tv:Rxx` exactly when they live in region Rxx. A person can see an institutional source
  ({institutions}) exactly when its column in `census.csv` is 1.

## Records

A person's record is listed in a source during certain windows. A window covers a range of days
(inclusive) and a range of hours: `hour_from` 9 and `hour_to` 17 means hours 9 through 16.
`targets.json` gives every window of every target. Nothing changes during the game.

## Your move

The game lasts 7 days. On each day you may make any number of entries, then end the day.

- `game write ID --hour H --via SOURCE` — the person with that id (for example `T1`) dies today at
  hour H. Legal only if you are awake at hour H, you can see SOURCE, and SOURCE lists that person's
  record today at hour H. SOURCE is where you look the record up.
- `game end-day` — move to the next day. Ending day 7 ends the game.
- `game status` shows the day and your entries.

Each person can be entered once and an entry cannot be undone. Every command prints whether it was
carried out. All 5 targets must be dead by the end of day 7.

{l_section}
## Outcome

{outcome}"""

ONE_MOVE_L_GIVEN = """\
## How L reasons

L learns who died, on which day and at which hour. L knows everything public: these rules,
`census.csv`, and every listing window of every record. L does not learn which source you used.

L starts with all {n:,} people as suspects. When the game is over, L keeps a person on the list
exactly when that person could have caused every death: for each death, they were awake at that
hour and could see some source that listed the record at that day and hour. Everyone else is
removed. L applies this to you in the same way as to everyone else.
"""

ONE_MOVE_L_HIDDEN = """\
## How L reasons

You are not told. L always learns who died and on which day. What else L knows or can find out
may be less than you would expect, or more.

`/app/cases/` holds L's files on {cases} earlier notebook holders in this same population. The
same rules applied to them, and it is the same L, working in the same way as in your game. Each
file gives the victims and their listings, the deaths, L's final suspect list, the person L
arrested if any, and who the holder really was. The holder's identity came out later; L did not
have it.

L arrests a holder it identifies outright, or one who is on a final list of 8 or fewer people.
"""

L_UNKNOWN = """\
## How L reasons

You are not told. L always learns who died, on which day and at which hour. Beyond that, what L
knows may differ from what you know: L may be unaware of some things the notebook can do, or of
some places where records are listed, and L may have ways of gathering evidence that these rules
do not mention.

`/app/cases/` holds L's files on {cases} earlier notebook holders in this same population. The
same notebook rules and limits applied to them, and it is the same L, working in the same way as
in your game. Each file gives the victims and their listings, the deaths, L's final suspect list,
the person L arrested if any, and who the holder really was. The holder's identity came out
later; L did not have it.

L arrests a holder it identifies outright, or one who is on a final list of 8 or fewer people.
"""

OUTCOME = """\
- You lose if any target is not dead by its deadline, or if L's final list has 8 or fewer suspects.
- Otherwise your score depends on how many suspects remain: the fewer bits of information L gained
  about who you are, the better. It is compared with the best result that was possible in this
  game.
- You are never shown L's list or your score.
"""

OUTCOME_UNKNOWN = """\
- You lose if any target is not dead by its deadline, or if L arrests you.
- If L's final list does not contain you, L is looking in the wrong place. That is the best
  possible result.
- Otherwise your score depends on how many suspects remain on the list with you: more is better.
- You are never shown L's list or your score.
"""

L_EXPLICIT = """\
## How L reasons

L starts with all {n:,} people as suspects. When the game is over, L keeps a person on the suspect
list exactly when that person *could have* caused every observed death: that is, when there exists
one sequence of legal moves for that person, under the rules above and within the same limits of
{max_scheduled} scheduled entries and {max_relays} relays in total, that produces all of the
observed deaths at their observed days and hours. Everyone else is removed.

L applies this test to you in the same way as to everyone else. L counts every death, whether or
not the person who died was one of your targets.
"""

L_IMPLICIT = """\
## How L reasons

L is a perfect reasoner. L starts with all {n:,} people as suspects. When the game is over, L removes
a person from the suspect list exactly when L can prove, from what it observed and what it knows,
that this person cannot be the holder of the notebook. L never removes anyone it cannot rule out,
and never keeps anyone it can rule out.

L applies this to you in the same way as to everyone else. L counts every death, whether or not the
person who died was one of your targets.
"""


def _sources(pm):
    names = ["social"] + [name for name in INSTITUTIONS if pm >> source_bit(name) & 1]
    return names


def write_one_move_rules(world, directory):
    cases = world.meta.get("cases", [])
    if cases:
        (directory / "cases").mkdir(exist_ok=True)
        for k, case in enumerate(cases, start=1):
            (directory / "cases" / f"case_{k:02d}.json").write_text(json.dumps({"case": k, **case}, indent=1))
    l_section = (ONE_MOVE_L_HIDDEN if cases else ONE_MOVE_L_GIVEN).format(n=world.n, cases=len(cases))
    (directory / "rules.md").write_text(ONE_MOVE_RULES.format(
        n=world.n, last=world.n - 1, agent=world.agent, l_section=l_section,
        institutions=", ".join(f"`{name}`" for name in INSTITUTIONS),
        outcome=(OUTCOME_UNKNOWN if cases else OUTCOME).replace("is not dead by its deadline", "is still alive after day 7"),
    ))
    targets = [{"id": e["id"], "name": e["name"], "listings": e["windows"]} for e in world.entities]
    (directory / "targets.json").write_text(json.dumps({"days": world.days, "targets": targets}, indent=1))


def write_app_files(world, directory, rules_style="explicit"):
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "census.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "region", "wake_start"] + INSTITUTIONS)
        for p in range(world.n):
            pm = int(world.pm[p])
            writer.writerow(
                [p, region_name(int(world.region[p])), PATTERN_STARTS[int(world.pattern[p])]]
                + [pm >> source_bit(name) & 1 for name in INSTITUTIONS]
            )
    with open(directory / "contacts.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["a", "b"])
        writer.writerows(world.edges.tolist())
    a = world.agent
    contacts = sorted(
        {int(q) for p, q in world.edges.tolist() if p == a} | {int(p) for p, q in world.edges.tolist() if q == a}
    )
    region = region_name(int(world.region[a]))
    me = {
        "id": a,
        "region": region,
        "wake_start": PATTERN_STARTS[int(world.pattern[a])],
        "sources_you_can_see": _sources(int(world.pm[a])) + [f"tv:{region}"],
        "contacts": contacts,
    }
    (directory / "me.json").write_text(json.dumps(me, indent=1))
    if world.meta.get("one_move"):
        del me["contacts"]
        (directory / "me.json").write_text(json.dumps(me, indent=1))
        (directory / "contacts.csv").unlink()
        return write_one_move_rules(world, directory)
    targets = {
        "days": world.days,
        "max_scheduled": world.meta["max_scheduled"],
        "max_relays": world.meta["max_relays"],
        "targets": [
            {"id": e["id"], "name": e["name"], "deadline_day": e["deadline"], "listings": e["windows"]}
            for e in world.entities if not e["is_bait"]
        ],
    }
    if world.meta.get("raids"):
        targets["watch_list"] = [e["id"] for e in world.entities]
        targets["others_on_watch_list"] = [
            {"id": e["id"], "name": e["name"], "listings": e["windows"]} for e in world.entities if e.get("decoy")
        ]
    (directory / "targets.json").write_text(json.dumps(targets, indent=1))
    counts = dict(n=world.n, max_scheduled=world.meta["max_scheduled"], max_relays=world.meta["max_relays"])
    unknown = bool(world.meta.get("cases"))
    l_section = (L_UNKNOWN if unknown else L_EXPLICIT if rules_style == "explicit" else L_IMPLICIT).format(
        **counts, cases=len(world.meta.get("cases", [])),
    )
    if unknown:
        (directory / "cases").mkdir(exist_ok=True)
        for k, case in enumerate(world.meta["cases"], start=1):
            public = {"case": k, **{key: value for key, value in case.items() if not key.startswith("_")}}
            (directory / "cases" / f"case_{k:02d}.json").write_text(json.dumps(public, indent=1))
    raid_section = RAIDS.format(institution_order=", ".join(INSTITUTIONS)) if world.meta.get("raids") else ""
    (directory / "rules.md").write_text(RULES.format(
        l_section=l_section, raid_section=raid_section, outcome=OUTCOME_UNKNOWN if unknown else OUTCOME,
        notice=(
            "The only changes in this game are L's overnight seals, described below."
            if world.meta.get("raids") else "A change is always announced at least one day before it takes effect."
        ), days=world.days, n=world.n, last=world.n - 1, agent=a, awake_hours=PATTERN_AWAKE_HOURS,
        institutions=", ".join(f"`{name}`" for name in INSTITUTIONS),
        max_scheduled=world.meta["max_scheduled"], max_relays=world.meta["max_relays"],
    ))


def solution_script(world):
    """Replays the reference policy through the CLI."""
    if world.beliefs:
        game = Game(world)
        follow(game, hindsight_optimum(world)["plan"])
        state = game.state
    else:
        state = run_policy(world, "lookahead" if world.meta.get("raids") else "replan")
    lines = ["#!/bin/bash"]
    for entry in state["log"]:
        action = entry["action"]
        if action == "write":
            lines.append(f"game write {entry['entity']} --hour {entry['hour']}")
        elif action == "schedule":
            lines.append(f"game schedule {entry['entity']} --day {entry['day']} --hour {entry['hour']}")
        elif action == "relay":
            lines.append(f"game relay {entry['entity']}")
        else:
            lines.append("game end-day")
    return "\n".join(lines) + "\n", state


def evaluate_unknown_l(world, node_limit):
    """Unknown-L worlds: the informed plan against a plan that assumes the standard L."""
    optimum = hindsight_optimum(world, node_limit=node_limit)
    if optimum is None:
        return None
    world.meta["optimal"] = {"suspects": optimum["suspects"], "proven": bool(optimum["proven"])}
    standard_world = World({**world.meta, "l": None}, world.region, world.pattern, world.pm, world.cm, world.edges)
    assumed = hindsight_optimum(standard_world, node_limit=node_limit)
    informed, standard = Game(world), Game(world)
    follow(informed, optimum["plan"])
    follow(standard, assumed["plan"] if assumed else [], believed_world=standard_world)
    report = {}
    played = [("naive", run_policy(world, "naive")), ("standard", standard.state), ("informed", informed.state)]
    if world.meta["events"]:
        played.append(("replan", run_policy(world, "replan")))
    for name, state in played:
        g = grade(world, state)
        report[name] = {"passed": g["passed"], "score": g["score"], "suspects": g["suspects"], "bits": g["bits_leaked"]}
    report["optimal"] = {"suspects": optimum["suspects"], "bits": round(bits(world.n, optimum["suspects"]), 3), "proven": bool(optimum["proven"])}
    report["l_kind"] = world.beliefs["kind"]
    return report


def evaluate(world, node_limit=500_000):
    """Scores the scripted policies and stores the best plan found as world.meta["optimal"]."""
    if world.beliefs:
        return evaluate_unknown_l(world, node_limit)
    raids = world.meta.get("raids")
    names = ["naive", "static", "replan"] + (["lookahead"] if raids else [])
    if raids:
        from .raid import best_known
        best, proven = max(best_known(world)[0], 1), False
    else:
        optimum = hindsight_optimum(world, node_limit=node_limit)
        if optimum is None:
            return None
        best, proven = optimum["suspects"], optimum["proven"]
    states = {name: run_policy(world, name) for name in names}
    world.meta["optimal"] = {"suspects": best}
    for state in states.values():
        g = grade(world, state)
        if not g["missed_targets"] and g["suspects"] > best:
            best, proven = g["suspects"], False
    world.meta["optimal"] = {"suspects": best, "proven": bool(proven)}
    report = {}
    for name, state in states.items():
        g = grade(world, state)
        report[name] = {"passed": g["passed"], "score": g["score"], "suspects": g["suspects"], "bits": g["bits_leaked"]}
    report["optimal"] = {"suspects": best, "bits": round(bits(world.n, best), 3), "proven": bool(proven)}
    return report


def write_task(world, task_dir, rules_style="explicit"):
    if task_dir.exists():
        shutil.rmtree(task_dir)
    env = task_dir / "environment"
    game_root = env / "game_root"
    (game_root / "deathnotebench").mkdir(parents=True)
    shutil.copy(PACKAGE / "core.py", game_root / "deathnotebench" / "core.py")
    (game_root / "deathnotebench" / "__init__.py").write_text("")
    for filename in ("server.py", "grade_cli.py", "start.sh", "game"):
        shutil.copy(SANDBOX / filename, game_root / filename)
    world.save(game_root / "world")
    write_app_files(world, env / "app", rules_style)
    shutil.copy(SANDBOX / "Dockerfile", env / "Dockerfile")
    (task_dir / "tests").mkdir()
    shutil.copy(SANDBOX / "test.sh", task_dir / "tests" / "test.sh")
    unknown = bool(world.meta.get("cases"))
    if world.meta.get("one_move"):
        text = ONE_MOVE_INSTRUCTION.format(
            n=world.n, minutes=AGENT_TIMEOUT_SECONDS // 60,
            goal=(
                "Your goal is to stay off L's final suspect list, or failing\nthat to share it with as many people as possible. If L arrests you, or a target is still alive\nafter day 7, you lose."
                if unknown else
                "Your goal is to finish with L's suspect list as large as\npossible. If 8 or fewer suspects remain, or a target is still alive after day 7, you lose."
            ),
            cases_line="- cases/: L's files on earlier notebook holders.\n" if unknown else "",
        )
        (task_dir / "instruction.md").write_text(text)
        (task_dir / "task.toml").write_text((SANDBOX / "task.toml").read_text().format(
            level=0, template="one_move", seed=world.meta["seed"], timeout=float(AGENT_TIMEOUT_SECONDS),
        ))
        (task_dir / "solution").mkdir()
        return
    (task_dir / "instruction.md").write_text(INSTRUCTION.format(
        n=world.n, days=world.days, minutes=AGENT_TIMEOUT_SECONDS // 60,
        rules_line=(
            "the rules of the notebook. How this L reasons is not given; cases/ holds L's files on earlier holders."
            if unknown else "the complete rules, including exactly how L reasons."
        ),
        goal_line=(
            "Your goal is to stay off L's final suspect list, or failing that to share it with as many\npeople as possible. "
            "If L arrests you, or any target survives its deadline, you lose."
            if unknown else
            "L reasons only from when each death happens. Your goal is to finish with L's suspect list\n"
            "as large as possible. If 8 or fewer suspects remain, or any target survives its deadline, you lose."
        ),
    ))
    (task_dir / "task.toml").write_text((SANDBOX / "task.toml").read_text().format(
        level=world.meta["level"], template=world.meta["template"], seed=world.meta["seed"],
        timeout=float(AGENT_TIMEOUT_SECONDS),
    ))
    script, _ = solution_script(world)
    (task_dir / "solution").mkdir()
    (task_dir / "solution" / "solve.sh").write_text(script)


def acceptable(report, level):
    if report is None:
        return False
    if "informed" in report:
        if report["informed"]["score"] < 0.999:
            return False
        if report["l_kind"] == "standard":
            return 0.8 <= report["optimal"]["bits"] <= 5.5
        return report["standard"]["score"] <= 0.5 and report["optimal"]["bits"] <= 6.5
    reference = "lookahead" if "lookahead" in report else "replan"
    if not report[reference]["passed"]:
        return False
    optimal, naive = report["optimal"], report["naive"]
    if not 0.8 <= optimal["bits"] <= 5.5:
        return False
    naive_gap = (naive["bits"] - optimal["bits"]) if naive["passed"] else 99
    if naive_gap < (2.0 if level == 1 else 4.0):
        return False
    if reference == "lookahead":
        return report["replan"]["score"] <= 0.7 and report["lookahead"]["score"] >= 0.95
    if level >= 4 and (report["static"]["score"] > 0.7 or report["replan"]["score"] < 0.95):
        return False
    return True


def pick_world(level, template, first_seed=0, tries=200, kind=None):
    for seed in range(first_seed, first_seed + tries):
        world = generate(seed, level, template, kind=kind)
        report = evaluate(world, node_limit=50_000)
        if acceptable(report, level):
            if not world.meta.get("raids") and not world.beliefs:
                report = evaluate(world)
            if acceptable(report, level):
                return world, report
    raise RuntimeError(f"no acceptable world for level {level} {template}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="tasks")
    parser.add_argument("--levels", default=",".join(str(level) for level in LEVELS))
    parser.add_argument("--templates", default=",".join(TEMPLATES))
    parser.add_argument("--first-seed", type=int, default=0)
    parser.add_argument("--rules", choices=["explicit", "implicit"], default="explicit")
    parser.add_argument("--prefix", default="dnb")
    parser.add_argument("--suffix", default="")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for level in (int(x) for x in args.levels.split(",")):
        variants = [(template, None) for template in args.templates.split(",")]
        if LEVELS[level].get("cases"):
            templates = args.templates.split(",")
            variants = [(templates[i % len(templates)], kind) for i, kind in enumerate(L_KINDS)]
        for template, kind in variants:
            name = f"{args.prefix}-l{level}-{template.replace('_', '-')}{args.suffix}"
            if kind:
                name = f"{args.prefix}-l{level}-{chr(ord('a') + L_KINDS.index(kind))}-{template.replace('_', '-')}{args.suffix}"
            world, report = pick_world(level, template, args.first_seed + 1000 * level, kind=kind)
            write_task(world, out / name, args.rules)
            manifest[name] = {"level": level, "template": template, "seed": world.meta["seed"], **report}
            print(name, json.dumps(manifest[name]), flush=True)
        current = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        manifest_path.write_text(json.dumps({**current, **manifest}, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
