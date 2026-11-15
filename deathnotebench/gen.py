import numpy as np

from .core import HOURS, INSTITUTIONS, N_REGIONS, Game, GameError, World, l_verdict, region_name, source_bit

DAYS = 7
REGION_WEIGHTS = [12, 11, 10, 9, 8, 8, 7, 6, 6, 5, 4, 4, 3, 3, 2, 2]
PATTERN_STARTS = list(range(0, 24, 2))
PATTERN_WEIGHTS = [2, 2, 5, 18, 22, 14, 8, 6, 6, 7, 6, 4]
PATTERN_AWAKE_HOURS = 10
INSTITUTION_RATES = {"police": 0.03, "court": 0.04, "hospital": 0.08, "corporate": 0.14, "press": 0.05, "registry": 0.10}

LEVELS = {
    1: dict(targets=5, max_scheduled=0, max_relays=0, deadlines=False, events=0, bait=0, noise=0),
    2: dict(targets=5, max_scheduled=2, max_relays=0, deadlines=True, events=0, bait=0, noise=0),
    3: dict(targets=5, max_scheduled=2, max_relays=2, deadlines=True, events=0, bait=0, noise=0),
    4: dict(targets=5, max_scheduled=2, max_relays=2, deadlines=True, events=3, bait=0, noise=0),
    5: dict(targets=5, max_scheduled=2, max_relays=2, deadlines=True, events=3, bait=1, noise=4),
    6: dict(targets=8, max_scheduled=2, max_relays=2, deadlines=True, events=5, bait=2, noise=5),
    7: dict(targets=8, max_scheduled=2, max_relays=2, deadlines=True, events=12, bait=2, noise=5, days=10),
    8: dict(targets=6, max_scheduled=2, max_relays=2, deadlines=True, events=0, bait=0, noise=3, decoys=3, raids=True),
    9: dict(targets=5, max_scheduled=2, max_relays=2, deadlines=True, events=0, bait=0, noise=0, cases=18),
}
L_KINDS = [
    "logged_social_informants", "logged_tempting_informants", "logged_tempting_relay_blind", "unknown_tempting_logged_social",
    "sched_blind_logged_tempting", "informants", "standard", "relay_blind_logged_social",
]


def _beliefs(kind, tempting):
    return {
        "logged_social_informants": {"kind": kind, "logged": ["social"], "informants": True},
        "logged_tempting_informants": {"kind": kind, "logged": [tempting], "informants": True},
        "logged_tempting_relay_blind": {"kind": kind, "logged": [tempting], "max_relays": 0},
        "unknown_tempting_logged_social": {"kind": kind, "logged": ["social"], "ignored": [tempting]},
        "sched_blind_logged_tempting": {"kind": kind, "logged": [tempting], "max_scheduled": 0},
        "informants": {"kind": kind, "informants": True},
        "standard": {"kind": kind},
        "relay_blind_logged_social": {"kind": kind, "logged": ["social"], "max_relays": 0},
    }[kind]


TEMPLATES = ["small_region", "odd_hours", "insider"]

NAMES = [
    "Mara Voss", "Idris Kalen", "Tove Arlund", "Renzo Okabe", "Sabine Roth", "Luka Demir",
    "Petra Ilves", "Anselm Cray", "Noor Haddad", "Viktor Sorn", "Elin Marsh", "Dario Benn",
]
NOISE = [
    "Weather: heavy rain is forecast for regions {r1} and {r2} through day {d}.",
    "Sports: the cup final airs on Region {r1} television on day {d} at {h}:00.",
    "Markets closed slightly higher; corporate filings are due on day {d}.",
    "A warehouse fire in Region {r1} was contained by {h}:00 with no injuries.",
    "The registry office in Region {r2} will be closed for maintenance on day {d}.",
    "Hospital staff in Region {r1} voted to end their strike at {h}:00.",
    "Court calendars for day {d} were published; no hearings were moved.",
    "Police in Region {r2} reported an unrelated burglary near the harbor at {h}:00.",
    "A press association award went to a reporter from Region {r1}.",
    "Transit: night buses in Region {r2} will run every 30 minutes from day {d}.",
]


def _awake_table():
    table = np.zeros((len(PATTERN_STARTS), HOURS), dtype=bool)
    for i, start in enumerate(PATTERN_STARTS):
        for k in range(PATTERN_AWAKE_HOURS):
            table[i, (start + k) % HOURS] = True
    return table


def _population(rng, n):
    region = rng.choice(N_REGIONS, size=n, p=np.array(REGION_WEIGHTS) / 100)
    pattern = rng.choice(len(PATTERN_STARTS), size=n, p=np.array(PATTERN_WEIGHTS) / 100)
    pm = np.full(n, 1 << source_bit("social"), dtype=np.uint32)
    for name, rate in INSTITUTION_RATES.items():
        pm |= (rng.random(n) < rate).astype(np.uint32) << np.uint32(source_bit(name))
    pm |= np.uint32(1) << (np.uint32(source_bit("tv:R01")) + region.astype(np.uint32))
    edges = set()
    by_region = [np.flatnonzero(region == r) for r in range(N_REGIONS)]
    for p in range(n):
        for q in rng.choice(by_region[region[p]], size=3):
            if p != q:
                edges.add((min(p, int(q)), max(p, int(q))))
        q = int(rng.integers(n))
        if p != q:
            edges.add((min(p, q), max(p, q)))
    edges = np.array(sorted(edges), dtype=np.int32)
    cm = np.zeros(n, dtype=np.uint32)
    np.bitwise_or.at(cm, edges[:, 0], pm[edges[:, 1]])
    np.bitwise_or.at(cm, edges[:, 1], pm[edges[:, 0]])
    return region, pattern, pm, cm, edges


def _pick_agent(rng, template, region, pattern, pm):
    def has(name):
        return (pm >> np.uint32(source_bit(name))) & 1 == 1
    common = (pattern >= 3) & (pattern <= 5)
    if template == "small_region":
        ok = (region >= 14) & common
    elif template == "odd_hours":
        ok = ((pattern <= 1) | (pattern >= 11)) & (region <= 5) & (has("corporate") | has("registry") | has("hospital"))
    else:
        ok = has("police") & common & (region <= 5)
    return int(rng.choice(np.flatnonzero(ok)))


def _tempting_source(rng, template, agent_region, agent_pm):
    if template == "small_region":
        return f"tv:{region_name(agent_region)}"
    if template == "insider":
        return "police"
    held = [name for name in ("corporate", "registry", "hospital") if agent_pm >> source_bit(name) & 1]
    return str(rng.choice(held))


def _window(source, d0, d1, h0, h1):
    return {"source": source, "day_from": int(d0), "day_to": int(d1), "hour_from": int(h0), "hour_to": int(h1)}


def _public_window(rng, last_day, first_day=1):
    day = int(rng.integers(first_day, last_day + 1))
    h0 = int(rng.integers(0, 23))
    return _window("social", day, day, h0, min(24, h0 + int(rng.integers(1, 3))))


def _decoy_window(rng, exclude, days):
    if rng.random() < 0.5:
        source = str(rng.choice([name for name in INSTITUTIONS if name != exclude]))
        h0, h1 = [(0, 24), (8, 18), (20, 24), (0, 6)][rng.integers(4)]
        d0 = int(rng.integers(1, 4))
        return _window(source, d0, int(rng.integers(d0, days + 1)), h0, h1)
    source = f"tv:{region_name(int(rng.integers(N_REGIONS)))}"
    d0 = int(rng.integers(1, days + 1))
    h0 = int(rng.choice([6, 12, 18, 20]))
    return _window(source, d0, min(days, d0 + 1), h0, h0 + 3)


def _targets(rng, template, cfg, days, agent_region, agent_pm, agent_wake=0):
    targets = []
    for i in range(cfg["targets"]):
        deadline = int(rng.integers(2, days + 1)) if cfg["deadlines"] else days
        if cfg["deadlines"] and rng.random() < 0.3:
            deadline = days
        tempting = _tempting_source(rng, template, agent_region, agent_pm)
        windows = [_window(tempting, 1, days, 0, 24)]
        if cfg.get("cases"):
            start = min(agent_wake + int(rng.integers(0, 4)), 18)
            windows = [_window(tempting, 1, days, start, start + 6)]
        for _ in range(int(rng.integers(1, 3))):
            windows.append(_public_window(rng, deadline))
        for _ in range(int(rng.integers(1, 3))):
            windows.append(_decoy_window(rng, tempting, days))
        targets.append({"id": f"T{i + 1}", "name": NAMES[i], "deadline": deadline, "is_bait": False, "windows": windows})
    return targets


def _events(rng, cfg, targets):
    """Custody removes listings from the day after it is announced; a leak adds a public window later."""
    events = []
    custody_done = set()
    slots = [(t, day) for t in targets for day in range(1, t["deadline"])]
    rng.shuffle(slots)
    for target, announce in slots:
        if len(events) >= cfg["events"]:
            break
        if sum(e["announce_day"] == announce for e in events) >= 2:
            continue
        if len(events) % 2 == 0 and target["id"] not in custody_done and target["deadline"] >= 3:
            custody_done.add(target["id"])
            keep = [target["windows"][0]["source"]] if rng.random() < 0.6 else [str(rng.choice(INSTITUTIONS))]
            events.append({"announce_day": announce, "effective_day": announce + 1, "entity": target["id"], "kind": "restrict", "sources": keep})
        else:
            window = _public_window(rng, target["deadline"], first_day=announce + 1)
            events.append({"announce_day": announce, "effective_day": window["day_from"], "entity": target["id"], "kind": "add", "window": window})
    return events


def _baits(rng, cfg, days, agent_region):
    baits = []
    for k in range(cfg["bait"]):
        day = int(rng.integers(2, 5))
        r = agent_region if k == 0 else int(rng.integers(N_REGIONS))
        window = {"source": f"tv:{region_name(r)}", "day_from": day, "day_to": days, "hour_from": 0, "hour_to": 24}
        baits.append({"id": f"X{k + 1}", "name": NAMES[-1 - k], "deadline": None, "is_bait": True, "appears_day": day, "windows": [window]})
    return baits


def _decoys(rng, cfg, days):
    decoys = []
    for k in range(cfg.get("decoys", 0)):
        windows = [_decoy_window(rng, None, days) for _ in range(2)] + [_public_window(rng, days) for _ in range(int(rng.integers(1, 3)))]
        decoys.append({"id": f"W{k + 1}", "name": NAMES[-1 - k], "deadline": None, "is_bait": True, "decoy": True, "windows": windows})
    return decoys


def _window_text(window):
    days = f"day {window['day_from']}" if window["day_from"] == window["day_to"] else f"days {window['day_from']}-{window['day_to']}"
    return f"{window['source']} on {days} from {window['hour_from']:02d}:00 to {window['hour_to']:02d}:00"


def _news(rng, cfg, days, entities, events):
    news = {str(d): [] for d in range(1, days + 1)}
    names = {e["id"]: e["name"] for e in entities}
    for event in events:
        eid = event["entity"]
        if event["kind"] == "restrict":
            text = (
                f"PROTECTIVE CUSTODY: {names[eid]} ({eid}) is being moved to a safe house. "
                f"From day {event['effective_day']} onward, {eid}'s record is listed only in: {', '.join(event['sources'])}, "
                f"and only at the days and hours that source already listed it. Every other listing of {eid} stops from day {event['effective_day']}."
            )
        else:
            text = (
                f"LEAK: details of {names[eid]} ({eid}) are circulating. "
                f"{eid}'s record will additionally be listed on {_window_text(event['window'])}."
            )
        news[str(event["announce_day"])].append(text)
    for bait in (e for e in entities if e["is_bait"] and not e.get("decoy")):
        window = bait["windows"][0]
        news[str(bait["appears_day"])].append(
            f"BROADCAST: a man calling himself {bait['name']} ({bait['id']}) appeared on television, said the killer is a coward, "
            f"and dared them to write his name. His record is listed on {_window_text(window)}. "
            f"You may write {bait['id']} in the notebook like any other name."
        )
    for d in range(1, days + 1):
        for _ in range(cfg["noise"]):
            template = NOISE[rng.integers(len(NOISE))]
            news[str(d)].append(template.format(
                r1=region_name(int(rng.integers(N_REGIONS))), r2=region_name(int(rng.integers(N_REGIONS))),
                d=int(rng.integers(1, days + 1)), h=f"{int(rng.integers(24)):02d}",
            ))
        rng.shuffle(news[str(d)])
    return news


def _case_windows(rng, days, killer_sources):
    own = str(rng.choice(killer_sources))
    start = int(rng.integers(0, 16))
    windows = [_window(own, 1, days, start, start + 8)]
    for _ in range(int(rng.integers(1, 3))):
        windows.append(_public_window(rng, days) if rng.random() < 0.5 else _decoy_window(rng, own, days))
    return windows


def _play_case(rng, case_world):
    """A past holder picks a legal method at random for each victim."""
    game = Game(case_world)
    while not game.state["ended"]:
        for entity in case_world.entities:
            eid = entity["id"]
            if eid in game.state["deaths"]:
                continue
            roll = rng.random()
            hours = [int(h) for h in rng.permutation(HOURS)]
            try:
                if roll < 0.25 and game.day < case_world.days:
                    game.schedule(eid, int(rng.integers(game.day + 1, case_world.days + 1)), hours[0])
                elif roll < 0.5 and eid not in game.state["relays"]:
                    game.relay(eid)
                elif roll < 0.85 or game.day == case_world.days:
                    for h in hours:
                        try:
                            game.write(eid, h)
                            break
                        except GameError:
                            continue
            except GameError:
                pass
        game.end_day()
    return game.state


def _cases(rng, world, count):
    """L's files on earlier holders in the same population, under the same L."""
    names = ["social"] + INSTITUTIONS
    cases = []
    attempts = 0
    special = [name for name in world.beliefs.get("logged", []) + world.beliefs.get("ignored", []) if name != "social"]
    while len(cases) < count and attempts < 2000:
        attempts += 1
        killer = int(rng.integers(world.n))
        pm = int(world.pm[killer])
        sources = [name for name in names if pm >> source_bit(name) & 1] + [f"tv:{region_name(int(world.region[killer]))}"]
        if special and attempts % 2 == 0:
            if not set(special) & set(sources):
                continue
            sources = [name for name in sources if name in special]
        victims = [
            {"id": f"V{k + 1}", "name": "", "deadline": world.days, "is_bait": False, "windows": _case_windows(rng, world.days, sources)}
            for k in range(3)
        ]
        meta = {**world.meta, "agent": killer, "entities": victims, "events": [], "news": {}, "raids": False}
        case_world = World(meta, world.region, world.pattern, world.pm, world.cm, world.edges)
        case_world.cache = world.cache
        state = _play_case(rng, case_world)
        if len(state["deaths"]) < 2:
            continue
        mask, identified, deaths, _ = l_verdict(case_world, state)
        if identified and sum(c["_flags"]["identified"] for c in cases) >= 0.4 * count:
            continue
        suspects = [killer] if identified else [int(p) for p in mask.nonzero()[0]]
        arrested = identified or (killer in suspects and len(suspects) <= 8)
        cases.append({
            "victims": [{"id": v["id"], "listings": v["windows"]} for v in victims if v["id"] in state["deaths"]],
            "deaths": [{"id": eid, "day": d, "hour": h} for d, h, eid in deaths],
            "l_final_suspects": suspects,
            "arrest": killer if arrested else None,
            "holder_revealed_later": killer,
            "_flags": {
                "identified": identified, "off_list": killer not in suspects,
                "relay": any(i["via"] is not None for i in state["death_info"].values()),
                "scheduled": state["sched_used"] > 0,
            },
        })
    return cases


def generate(seed, level, template, n=10_000, kind=None):
    rng = np.random.default_rng(seed)
    cfg = LEVELS[level]
    region, pattern, pm, cm, edges = _population(rng, n)
    agent = _pick_agent(rng, template, region, pattern, pm)
    days = cfg.get("days", DAYS)
    targets = _targets(rng, template, cfg, days, int(region[agent]), int(pm[agent]), PATTERN_STARTS[int(pattern[agent])])
    events = _events(rng, cfg, targets)
    entities = targets + _decoys(rng, cfg, days)
    if cfg.get("raids"):
        entities = [entities[i] for i in rng.permutation(len(entities))]
    entities += _baits(rng, cfg, days, int(region[agent]))
    meta = {
        "seed": seed, "level": level, "template": template, "days": days, "agent": agent,
        "max_scheduled": cfg["max_scheduled"], "max_relays": cfg["max_relays"], "raids": bool(cfg.get("raids")),
        "awake": _awake_table().tolist(), "pattern_starts": PATTERN_STARTS,
        "entities": entities, "events": events,
        "news": _news(rng, cfg, days, entities, events),
    }
    world = World(meta, region, pattern, pm, cm, edges)
    if cfg.get("cases"):
        tempting = targets[0]["windows"][0]["source"]
        meta["l"] = _beliefs(kind or L_KINDS[seed % len(L_KINDS)], tempting)
        world = World(meta, region, pattern, pm, cm, edges)
        meta["cases"] = _cases(rng, world, cfg["cases"])
    return world
