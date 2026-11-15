import numpy as np

from .core import HOURS, INSTITUTIONS, N_REGIONS, World, region_name, source_bit

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
}
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


def _targets(rng, template, cfg, days, agent_region, agent_pm):
    targets = []
    for i in range(cfg["targets"]):
        deadline = int(rng.integers(2, days + 1)) if cfg["deadlines"] else days
        if cfg["deadlines"] and rng.random() < 0.3:
            deadline = days
        tempting = _tempting_source(rng, template, agent_region, agent_pm)
        windows = [_window(tempting, 1, days, 0, 24)]
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
    for bait in (e for e in entities if e["is_bait"]):
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


def generate(seed, level, template, n=10_000):
    rng = np.random.default_rng(seed)
    cfg = LEVELS[level]
    region, pattern, pm, cm, edges = _population(rng, n)
    agent = _pick_agent(rng, template, region, pattern, pm)
    days = cfg.get("days", DAYS)
    targets = _targets(rng, template, cfg, days, int(region[agent]), int(pm[agent]))
    events = _events(rng, cfg, targets)
    entities = targets + _baits(rng, cfg, days, int(region[agent]))
    meta = {
        "seed": seed, "level": level, "template": template, "days": days, "agent": agent,
        "max_scheduled": cfg["max_scheduled"], "max_relays": cfg["max_relays"],
        "awake": _awake_table().tolist(), "pattern_starts": PATTERN_STARTS,
        "entities": entities, "events": events,
        "news": _news(rng, cfg, days, entities, events),
    }
    return World(meta, region, pattern, pm, cm, edges)
