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
    actions could have produced every observed death (entity, day, hour)."""

    def __init__(self, world, lm):
        self.world = world
        self.max_sched = world.meta["max_scheduled"]
        self.max_relay = world.meta["max_relays"]
        self.awake = world.awake[world.pattern]
        self.own = (world.pm[None, None, None, :] & lm[..., None]) != 0
        own_write = (self.own & self.awake.T[None, None]).any(axis=2)
        day_or = np.bitwise_or.reduce(lm, axis=2)
        self.relayable = (world.cm[None, None, :] & day_or[..., None]) != 0
        self.own_write = own_write
        zeros = np.zeros_like(own_write[:, :1])
        # sched_own[e, d]: could have written e on some day before d from own access
        self.sched_own = np.concatenate([zeros, np.logical_or.accumulate(own_write, axis=1)[:, :-1]], axis=1)
        # sched_relay[e, d]: a relay requested on day y could be written on y+1 < d
        rel_cum = np.logical_or.accumulate(self.relayable, axis=1)
        self.sched_relay = np.concatenate([zeros, zeros, rel_cum[:, :-2]], axis=1)

    def modes(self, e, d, h):
        awake = self.awake[:, h]
        direct_own = awake & self.own[e, d, h]
        direct_relay = awake & self.relayable[e, d - 1] if d >= 2 else np.zeros_like(awake)
        sched_own = self.sched_own[e, d] if self.max_sched else np.zeros_like(awake)
        sched_relay = self.sched_relay[e, d] if self.max_sched else np.zeros_like(awake)
        if not self.max_relay:
            direct_relay = np.zeros_like(awake)
            sched_relay = np.zeros_like(awake)
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
        state = self.initial_state()
        for e, d, h in deaths:
            state = self.step(state, self.modes(e, d, h))
        return state[-1, -1]

    def trace(self, deaths):
        """Suspect count after each death, in the order given."""
        state = self.initial_state()
        counts = []
        for e, d, h in deaths:
            state = self.step(state, self.modes(e, d, h))
            counts.append(int(state[-1, -1].sum()))
        return counts


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
        self.lm = world.listing()
        self.pm = int(world.pm[world.agent])
        self.cm = int(world.cm[world.agent])
        self.awake = world.awake[world.pattern[world.agent]]
        self.state = state or {
            "day": 1, "ended": False, "deaths": {}, "relays": {},
            "sched_used": 0, "relay_used": 0, "log": [],
        }

    @property
    def day(self):
        return self.state["day"]

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

    def _can_write_today(self, e):
        return any(self.awake[h] and self._own_at(e, self.day, h) for h in range(HOURS))

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
        self._record_death("write", eid, self.day, hour)

    def schedule(self, name, day, hour):
        eid, e = self._entity(name)
        if self.state["sched_used"] >= self.world.meta["max_scheduled"]:
            raise GameError("no scheduled entries left")
        if not (self.day < day <= self.world.days and 0 <= hour < HOURS):
            raise GameError(f"scheduled entries take effect on a later day (up to day {self.world.days}), hour 0-23")
        if not (self._can_write_today(e) or self._holds_relay(eid)):
            raise GameError(f"you cannot see {eid}'s record at any hour you are awake today and hold no relayed copy")
        self.state["sched_used"] += 1
        self._record_death("schedule", eid, day, hour)

    def relay(self, name):
        eid, e = self._entity(name)
        if self.state["relay_used"] >= self.world.meta["max_relays"]:
            raise GameError("no relays left")
        if not (self.cm & int(np.bitwise_or.reduce(self.lm[e, self.day]))):
            raise GameError(f"none of your contacts can see {eid}'s record today")
        self.state["relay_used"] += 1
        self.state["relays"][eid] = self.day + 1
        self.state["log"].append({"action": "relay", "entity": eid, "on_day": self.day})

    def _record_death(self, action, eid, day, hour):
        self.state["deaths"][eid] = [day, hour]
        self.state["log"].append({"action": action, "entity": eid, "on_day": self.day, "day": day, "hour": hour})

    def end_day(self):
        if self.state["ended"]:
            raise GameError("the game is over")
        self.state["log"].append({"action": "end-day", "on_day": self.day})
        if self.day >= self.world.days:
            self.state["ended"] = True
        else:
            self.state["day"] += 1

    def news(self, day=None):
        return self.world.meta["news"].get(str(day or self.day), [])


def grade(world, state):
    lf = LFilter(world, world.listing())
    deaths = sorted(
        ((d, h, eid) for eid, (d, h) in state["deaths"].items()),
    )
    ordered = [(world.index[eid], d, h) for d, h, eid in deaths]
    counts = lf.trace(ordered)
    suspects = counts[-1] if counts else world.n
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
        "missed_targets": missed,
        "bait_taken": baits,
        "scheduled_used": state["sched_used"],
        "relays_used": state["relay_used"],
        "events": events,
        "log": state["log"],
    }
