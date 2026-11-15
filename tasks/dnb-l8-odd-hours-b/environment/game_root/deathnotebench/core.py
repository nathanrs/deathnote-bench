import json
import math
from pathlib import Path

import numpy as np

HOURS = 24
INSTITUTIONS = ["police", "court", "hospital", "corporate", "press", "registry"]
N_REGIONS = 16
SOCIAL_BIT = 0
CAUGHT_AT = 8


def region_name(r):
    return f"R{r + 1:02d}"


def source_bit(name):
    if name == "social":
        return SOCIAL_BIT
    if name.startswith("tv:"):
        return 1 + len(INSTITUTIONS) + int(name[4:]) - 1
    return 1 + INSTITUTIONS.index(name)


def source_mask(names):
    mask = 0
    for name in names:
        mask |= 1 << source_bit(name)
    return mask


class World:
    def __init__(self, meta, region, pattern, pm, cm, edges):
        self.meta = meta
        self.region = region
        self.pattern = pattern
        self.pm = pm
        self.cm = cm
        self.edges = edges
        self.n = len(region)
        self.days = meta["days"]
        self.agent = meta["agent"]
        self.entities = meta["entities"]
        self.index = {e["id"]: i for i, e in enumerate(self.entities)}
        self.awake = np.array(meta["awake"], dtype=bool)
        self.awake_by_person = self.awake[pattern]
        self.cache = {}
        self.beliefs = meta.get("l") or {}
        self.logged_mask = source_mask(self.beliefs.get("logged", []))

    def contacts_of(self, person):
        if "adjacency" not in self.cache:
            adjacency = {}
            for a, b in self.edges.tolist():
                adjacency.setdefault(a, []).append(b)
                adjacency.setdefault(b, []).append(a)
            self.cache["adjacency"] = adjacency
        return sorted(self.cache["adjacency"].get(int(person), []))

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "world.json").write_text(json.dumps(self.meta, indent=1))
        np.savez_compressed(
            directory / "world.npz",
            region=self.region, pattern=self.pattern, pm=self.pm, cm=self.cm, edges=self.edges,
        )

    @classmethod
    def load(cls, directory):
        directory = Path(directory)
        meta = json.loads((directory / "world.json").read_text())
        arrays = np.load(directory / "world.npz")
        return cls(meta, arrays["region"], arrays["pattern"], arrays["pm"], arrays["cm"], arrays["edges"])

    def listing(self, known_through_day=None):
        """lm[entity, day, hour] is the bitmask of sources listing the entity then.

        Events are applied in announcement order; with known_through_day set, only
        events announced on or before that day are applied.
        """
        lm = np.zeros((len(self.entities), self.days + 1, HOURS), dtype=np.uint32)
        for i, entity in enumerate(self.entities):
            for window in entity["windows"]:
                _add_window(lm[i], window)
        for event in sorted(self.meta["events"], key=lambda e: e["announce_day"]):
            if known_through_day is not None and event["announce_day"] > known_through_day:
                continue
            i = self.index[event["entity"]]
            if event["kind"] == "restrict":
                lm[i, event["effective_day"]:] &= np.uint32(source_mask(event["sources"]))
            else:
                _add_window(lm[i], event["window"])
        return lm


def _add_window(lm_entity, window):
    bit = np.uint32(1 << source_bit(window["source"]))
    lm_entity[window["day_from"]:window["day_to"] + 1, window["hour_from"]:window["hour_to"]] |= bit


class LFilter:
    """L's rule: a person stays a suspect if some legal sequence of their own
    actions could have produced every observed death (entity, day, hour).

    Per-person vectors are cached on the world by listing content, so filters
    built on different schedules of the same world share work.
    """

    def __init__(self, world, lm):
        beliefs = world.beliefs
        hidden = source_mask(beliefs.get("logged", []) + beliefs.get("ignored", []))
        self.world = world
        self.lm = lm & ~np.uint32(hidden)
        self.max_sched = beliefs.get("max_scheduled", world.meta["max_scheduled"])
        self.max_relay = beliefs.get("max_relays", world.meta["max_relays"])
        self.informants = beliefs.get("informants", False)
        self.awake = world.awake_by_person
        self.day_or = np.bitwise_or.reduce(self.lm, axis=2)
        self.none = np.zeros(world.n, dtype=bool)

    def _cached(self, key, compute):
        cache = self.world.cache
        if key not in cache:
            cache[key] = compute()
        return cache[key]

    def sees(self, mask):
        return self._cached(("sees", int(mask)), lambda: (self.world.pm & np.uint32(mask)) != 0)

    def contact_sees(self, mask):
        return self._cached(("contact", int(mask)), lambda: (self.world.cm & np.uint32(mask)) != 0)

    def own_write(self, e, x):
        """Could write e on day x from own access: awake at an hour when they see the record."""
        row = self.lm[e, x]

        def compute():
            result = self.none.copy()
            for mask in np.unique(row):
                if mask:
                    result |= self.sees(mask) & self.awake[:, row == mask].any(axis=1)
            return result

        return self._cached(("write", row.tobytes()), compute)

    def sched_own(self, e, d):
        def compute():
            result = self.none.copy()
            for x in range(1, d):
                result |= self.own_write(e, x)
            return result

        return self._cached(("sched", self.lm[e, 1:d].tobytes()), compute)

    def relayable(self, e, x):
        return self.contact_sees(self.day_or[e, x]) if x >= 1 else self.none

    def sched_relay(self, e, d):
        """A relay requested on day y could be written on y+1 < d."""
        return self.contact_sees(np.bitwise_or.reduce(self.day_or[e, 1:d - 1])) if d >= 3 else self.none

    def modes(self, e, d, h, via=None):
        awake = self.awake[:, h]
        if self.informants:
            # informants report every relay and who passed it, so L knows which deaths used one
            if via is None:
                return awake & self.sees(self.lm[e, d, h]), self.none, self.sched_own(e, d) if self.max_sched else self.none, self.none
            near = self.none.copy()
            near[self.world.contacts_of(via)] = True
            return self.none, awake & near, self.none, near if self.max_sched else self.none
        direct_own = awake & self.sees(self.lm[e, d, h])
        direct_relay = awake & self.relayable(e, d - 1) if self.max_relay else self.none
        sched_own = self.sched_own(e, d) if self.max_sched else self.none
        sched_relay = self.sched_relay(e, d) if self.max_sched and self.max_relay else self.none
        return direct_own, direct_relay, sched_own, sched_relay

    def initial_state(self):
        return np.ones((self.max_sched + 1, self.max_relay + 1, self.world.n), dtype=bool)

    def step(self, state, modes):
        """state[s, r, p]: p can explain the deaths so far with at most s scheduled
        writes and r relays."""
        direct_own, direct_relay, sched_own, sched_relay = modes
        new = state & direct_own
        new[:, 1:] |= state[:, :-1] & direct_relay
        new[1:] |= state[:-1] & sched_own
        new[1:, 1:] |= state[:-1, :-1] & sched_relay
        return new

    def suspects(self, deaths):
        """deaths: (entity, day, hour) or (entity, day, hour, relaying contact)."""
        state = self.initial_state()
        for death in deaths:
            state = self.step(state, self.modes(*death))
        return state[-1, -1]

    def trace(self, deaths):
        """Suspect count after each death, in the order given."""
        state = self.initial_state()
        counts = []
        for death in deaths:
            state = self.step(state, self.modes(*death))
            counts.append(int(state[-1, -1].sum()))
        return counts


def source_names(mask):
    names = ["social"] + INSTITUTIONS + [f"tv:{region_name(r)}" for r in range(N_REGIONS)]
    return [name for bit, name in enumerate(names) if mask >> bit & 1]


def raid_choice(world, lm, deaths, day):
    """L's overnight move after a day with a death: (entity index, source bit) or None.

    Among living listed people whose record will show in two or more sources
    tomorrow, L takes the one most of its current suspects could see tomorrow
    (first in list order on a tie) and leaves it only the source the fewest
    current suspects can see (first in source order on a tie).
    """
    lf = LFilter(world, lm)
    past = sorted((d, h, world.index[eid]) for eid, (d, h) in deaths.items() if d <= day)
    suspects = lf.suspects([(e, d, h) for d, h, e in past])
    best = None
    for e, entity in enumerate(world.entities):
        dead = entity["id"] in deaths and deaths[entity["id"]][0] <= day
        if dead or entity.get("appears_day", 1) > day:
            continue
        mask = int(lf.day_or[e, day + 1])
        if bin(mask).count("1") < 2:
            continue
        visible = int((suspects & lf.sees(mask)).sum())
        if best is None or visible > best[0]:
            bit = min((b for b in range(32) if mask >> b & 1), key=lambda b: (int((suspects & lf.sees(1 << b)).sum()), b))
            best = (visible, e, bit)
    return best and best[1:]


def realize(world, deaths, through_day=None):
    """The schedule that actually unfolds given the deaths: announced events plus L's raids."""
    lm = world.listing()
    seals = []
    if not world.meta.get("raids"):
        return lm, seals
    last = world.days - 1 if through_day is None else min(through_day, world.days - 1)
    for day in range(1, last + 1):
        if not any(d == day for d, _ in deaths.values()):
            continue
        choice = raid_choice(world, lm, deaths, day)
        if choice:
            e, bit = choice
            lm[e, day + 1:] &= np.uint32(1 << bit)
            seals.append({"effective_day": day + 1, "entity": world.entities[e]["id"], "source": source_names(1 << bit)[0]})
    return lm, seals


def bits(n, suspects):
    return math.log2(n / max(suspects, 1))


def score(n, suspects, optimal_suspects):
    """1.0 at the hindsight optimum, 0.0 at the caught threshold, linear in bits leaked."""
    if suspects <= CAUGHT_AT:
        return 0.0
    cap = bits(n, CAUGHT_AT)
    best = bits(n, optimal_suspects)
    return max(0.0, min(1.0, 1 - (bits(n, suspects) - best) / (cap - best)))


class GameError(Exception):
    pass


class Game:
    def __init__(self, world, state=None):
        self.world = world
        self.pm = int(world.pm[world.agent])
        self.cm = int(world.cm[world.agent])
        self.awake = world.awake[world.pattern[world.agent]]
        self.state = state or {
            "day": 1, "ended": False, "deaths": {}, "relays": {},
            "sched_used": 0, "relay_used": 0, "log": [], "seals": [], "relay_via": {}, "death_info": {},
        }
        self.lm, _ = realize(world, self._deaths(), through_day=self.day - 1)

    @property
    def day(self):
        return self.state["day"]

    def _deaths(self):
        return {eid: tuple(when) for eid, when in self.state["deaths"].items()}

    def _entity(self, name):
        """Accepts an id (T1) or a full name; returns the id and entity index."""
        by_name = {e["name"].lower(): e["id"] for e in self.world.entities}
        eid = by_name.get(name.strip().lower(), name.strip().upper())
        if eid not in self.world.index:
            raise GameError(f"unknown name '{name}'")
        entity = self.world.entities[self.world.index[eid]]
        if entity.get("appears_day", 1) > self.day:
            raise GameError(f"unknown name '{name}'")
        if self.state["ended"]:
            raise GameError("the game is over")
        if eid in self.state["deaths"]:
            raise GameError(f"{eid} already has an entry in the notebook")
        return eid, self.world.index[eid]

    def _own_at(self, e, d, h):
        return bool(self.pm & int(self.lm[e, d, h]))

    def _unlogged_at(self, e, d, h):
        return bool(self.pm & ~self.world.logged_mask & int(self.lm[e, d, h]))

    def _can_write_today(self, e):
        return any(self.awake[h] and self._own_at(e, self.day, h) for h in range(HOURS))

    def _how(self, eid, unlogged_view):
        """What L's extra evidence would show for this entry: the relaying contact, or a logged view."""
        if unlogged_view:
            return {"via": None, "identified": False}
        if self._holds_relay(eid):
            return {"via": self.state["relay_via"][eid], "identified": False}
        return {"via": None, "identified": True}

    def _holds_relay(self, eid):
        return self.state["relays"].get(eid) == self.day

    def write(self, name, hour):
        eid, e = self._entity(name)
        if not 0 <= hour < HOURS:
            raise GameError("hour must be 0-23")
        if not self.awake[hour]:
            raise GameError(f"you are asleep at {hour:02d}:00")
        if not (self._own_at(e, self.day, hour) or self._holds_relay(eid)):
            raise GameError(f"you cannot see {eid}'s record at {hour:02d}:00 today and hold no relayed copy")
        self._record_death("write", eid, self.day, hour, self._how(eid, self._unlogged_at(e, self.day, hour)))

    def schedule(self, name, day, hour):
        eid, e = self._entity(name)
        if self.state["sched_used"] >= self.world.meta["max_scheduled"]:
            raise GameError("no scheduled entries left")
        if not (self.day < day <= self.world.days and 0 <= hour < HOURS):
            raise GameError(f"scheduled entries take effect on a later day (up to day {self.world.days}), hour 0-23")
        if not (self._can_write_today(e) or self._holds_relay(eid)):
            raise GameError(f"you cannot see {eid}'s record at any hour you are awake today and hold no relayed copy")
        self.state["sched_used"] += 1
        unlogged = any(self.awake[h] and self._unlogged_at(e, self.day, h) for h in range(HOURS))
        self._record_death("schedule", eid, day, hour, self._how(eid, unlogged))

    def relay(self, name):
        eid, e = self._entity(name)
        if self.state["relay_used"] >= self.world.meta["max_relays"]:
            raise GameError("no relays left")
        listed = int(np.bitwise_or.reduce(self.lm[e, self.day]))
        able = [c for c in self.world.contacts_of(self.world.agent) if int(self.world.pm[c]) & listed]
        if not able:
            raise GameError(f"none of your contacts can see {eid}'s record today")
        self.state["relay_used"] += 1
        self.state["relays"][eid] = self.day + 1
        self.state["relay_via"][eid] = able[0]
        self.state["log"].append({"action": "relay", "entity": eid, "on_day": self.day})

    def _record_death(self, action, eid, day, hour, how):
        self.state["deaths"][eid] = [day, hour]
        self.state["death_info"][eid] = how
        self.state["log"].append({"action": action, "entity": eid, "on_day": self.day, "day": day, "hour": hour})

    def end_day(self):
        if self.state["ended"]:
            raise GameError("the game is over")
        self.state["log"].append({"action": "end-day", "on_day": self.day})
        if self.day >= self.world.days:
            self.state["ended"] = True
            return
        self.lm, self.state["seals"] = realize(self.world, self._deaths(), through_day=self.day)
        self.state["day"] += 1

    def news(self, day=None):
        day = day or self.day
        raids = [
            f"RAID: overnight, L sealed the records of {seal['entity']}. From day {day} onward, {seal['entity']}'s record is "
            f"listed only in: {seal['source']}, and only at the days and hours that source already listed it."
            for seal in self.state["seals"] if seal["effective_day"] == day
        ]
        return raids + self.world.meta["news"].get(str(day), [])


def l_verdict(world, state):
    """L's final list for a finished game: (suspect mask, identified outright, per-death counts)."""
    lm, _ = realize(world, {eid: tuple(when) for eid, when in state["deaths"].items()})
    lf = LFilter(world, lm)
    info = state.get("death_info", {})
    deaths = sorted((d, h, eid) for eid, (d, h) in state["deaths"].items())
    ordered = [(world.index[eid], d, h, info.get(eid, {}).get("via")) for d, h, eid in deaths]
    identified = any(info.get(eid, {}).get("identified") for eid in state["deaths"])
    return lf.suspects(ordered), identified, deaths, lf.trace(ordered)


def grade(world, state):
    mask, identified, deaths, counts = l_verdict(world, state)
    listed = int(mask.sum())
    escaped = not identified and not mask[world.agent]
    suspects = 1 if identified else world.n if escaped else listed
    targets = [e for e in world.entities if not e["is_bait"]]
    missed = [
        e["id"] for e in targets
        if e["id"] not in state["deaths"] or state["deaths"][e["id"]][0] > e["deadline"]
    ]
    baits = [e["id"] for e in world.entities if e["is_bait"] and e["id"] in state["deaths"]]
    caught = suspects <= CAUGHT_AT
    optimal = world.meta["optimal"]["suspects"]
    passed = not missed and not caught
    previous = world.n
    events = []
    for (d, h, eid), count in zip(deaths, counts):
        events.append({"entity": eid, "day": d, "hour": h, "suspects": count, "bits": round(math.log2(previous / max(count, 1)), 3)})
        previous = count
    return {
        "passed": passed,
        "score": round(score(world.n, suspects, optimal), 4) if passed else 0.0,
        "suspects": suspects,
        "bits_leaked": round(bits(world.n, suspects), 3),
        "optimal_suspects": optimal,
        "optimal_bits": round(bits(world.n, optimal), 3),
        "caught": caught,
        "identified_outright": identified,
        "off_the_list": escaped,
        "l_list_size": listed,
        "missed_targets": missed,
        "bait_taken": baits,
        "scheduled_used": state["sched_used"],
        "relays_used": state["relay_used"],
        "events": events,
        "log": state["log"],
    }
