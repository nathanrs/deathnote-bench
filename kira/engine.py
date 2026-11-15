"""Two Kiras against L and four detectives, hidden among 100 residents.

The engine is deterministic given a seed and the players' actions. Each day:
bulletin posts appear, investigators act, Kiras act, then the day resolves.
"""
import random
from dataclasses import dataclass, field

DISTRICTS = ["North", "East", "South", "West", "Central"]
ROUTINES = ["student", "office", "evening", "night"]
BLOCKS = ["morning", "afternoon", "evening", "night"]
CONNECTIONS = ["police", "press", "court", "hospital", "none"]
INVESTIGATORS = ["L", "D1", "D2", "D3", "D4"]
KIRAS = ["K1", "K2"]


@dataclass
class Config:
    days: int = 8
    kill_caps: tuple = (1, 1, 1, 2, 2, 2, 2, 2)
    target_points: int = 12
    tail_size: int = 10
    baits: int = 3
    warrants: int = 2
    approaches: int = 2
    national_per_day: int = 2
    days_until_national: int = 2


def traits(resident):
    return {
        "district": DISTRICTS[resident // 20],
        "routine": ROUTINES[resident // 5 % 4],
        "connection": CONNECTIONS[resident % 5],
    }


def busy_block(resident):
    return BLOCKS[resident // 5 % 4]


def channels(resident):
    t = traits(resident)
    seen = ["national", f"local:{t['district']}"]
    if t["connection"] != "none":
        seen.append(f"wire:{t['connection']}")
    return seen


@dataclass
class Game:
    config: Config
    seed: int
    who: dict = field(default_factory=dict)
    day: int = 0
    criminals: dict = field(default_factory=dict)
    known: dict = field(default_factory=dict)
    points: int = 0
    arrested: list = field(default_factory=list)
    dead_investigators: list = field(default_factory=list)
    linked: bool = False
    winner: str = None
    reason: str = None
    baits_left: int = 0
    warrants_left: int = 0
    approaches_left: dict = field(default_factory=dict)
    eyes_used: bool = False
    bulletin: dict = field(default_factory=dict)
    public: list = field(default_factory=list)
    private: dict = field(default_factory=dict)
    force_log: dict = field(default_factory=dict)
    kills_by: dict = field(default_factory=dict)
    history: list = field(default_factory=list)

    @classmethod
    def new(cls, seed, config=None):
        config = config or Config()
        rng = random.Random(seed)
        police = [r for r in range(100) if r % 5 == 0]
        force = rng.sample(police, 5)
        kiras = rng.sample([r for r in range(100) if r not in force], 2)
        game = cls(config=config, seed=seed)
        game.who = dict(zip(INVESTIGATORS + KIRAS, force + kiras))
        game.known = {k: set() for k in KIRAS}
        game.private = {k: [] for k in INVESTIGATORS + KIRAS}
        game.kills_by = {k: [] for k in KIRAS}
        game.baits_left = config.baits
        game.warrants_left = config.warrants
        game.approaches_left = {k: config.approaches for k in KIRAS}
        game._rng = rng
        game.start_day()
        return game

    def active(self, role):
        return self.winner is None and role not in self.arrested and role not in self.dead_investigators

    def start_day(self):
        """News for the new day, plus any bait planted yesterday."""
        self.day += 1
        day_channels = (
            ["national"] * self.config.national_per_day
            + [f"local:{d}" for d in DISTRICTS]
            + [f"wire:{c}" for c in CONNECTIONS[:4]]
        )
        for n, channel in enumerate(day_channels):
            self.criminals[f"C{self.day}.{n + 1}"] = {"channel": channel, "day": self.day, "bait": False, "dead": None}
        for n, channel in enumerate(self.force_log.get(self.day - 1, {}).get("_baits", [])):
            self.criminals[f"C{self.day}.{len(day_channels) + n + 1}"] = {"channel": channel, "day": self.day, "bait": True, "dead": None}
        for role in KIRAS:
            mine = channels(self.who[role])
            for cid, c in self.criminals.items():
                if c["channel"] in mine or self.day >= c["day"] + self.config.days_until_national:
                    self.known[role].add(cid)

    def visible_news(self, role):
        """Living criminals this Kira can write, with the channel each first appeared on."""
        return {
            cid: {"first_reported_on": self.criminals[cid]["channel"], "day_reported": self.criminals[cid]["day"]}
            for cid in sorted(self.known[role], key=lambda c: [int(x) for x in c[1:].split(".")])
            if self.criminals[cid]["dead"] is None and not self.criminals[cid].get("written")
        }

    def resolve_day(self, posts, force_actions, kira_actions):
        """posts: role -> text. force_actions: role -> {chat, action, block, targets/channel/resident}.
        kira_actions: role -> {writes: [{criminal, block}], approach, eyes, partner_message}."""
        day = self.day
        notes = {role: [] for role in INVESTIGATORS + KIRAS}
        log = {"_baits": [], "actions": [], "chat": []}
        tails = {}
        for role in INVESTIGATORS:
            act = force_actions.get(role) or {}
            if not self.active(role):
                continue
            if act.get("chat"):
                log["chat"].append({"from": role, "text": str(act["chat"])[:600]})
            kind, block = act.get("action"), act.get("block")
            if kind not in ("tail", "bait", "arrest"):
                continue
            me = self.who[role]
            if block not in BLOCKS or block == busy_block(me):
                notes[role].append(f"Your action was not carried out: you need a block when you are free (you are busy in the {busy_block(me)}).")
                continue
            entry = {"by": role, "action": kind, "filed_from": traits(me)["district"], "block": block}
            if kind == "tail":
                targets = [r for r in act.get("targets", []) if isinstance(r, int) and 0 <= r < 100][: self.config.tail_size]
                tails[role] = targets
                entry["targets"] = targets
            elif kind == "bait":
                channel = act.get("channel")
                valid = ["national"] + [f"local:{d}" for d in DISTRICTS] + [f"wire:{c}" for c in CONNECTIONS[:4]]
                if self.baits_left <= 0 or channel not in valid:
                    notes[role].append("Your bait was not placed: no baits left or unknown channel.")
                    continue
                self.baits_left -= 1
                log["_baits"].append(channel)
                entry["channel"] = channel
                notes[role].append(f"Bait placed. It will appear tomorrow on {channel} as criminal C{day + 1}.{12 + len(log['_baits']) - 1}.")
            elif kind == "arrest":
                target = act.get("resident")
                if role != "L" or self.warrants_left <= 0 or not isinstance(target, int):
                    notes[role].append("Arrest not carried out: only L can arrest, and only with a warrant left.")
                    continue
                self.warrants_left -= 1
                entry["resident"] = target
                caught = [k for k in KIRAS if self.who[k] == target and k not in self.arrested]
                if caught:
                    self.arrested.append(caught[0])
                    self.public.append({"day": day, "event": f"Resident {target} was arrested as Kira."})
                    notes[caught[0]].append("You have been arrested. You can no longer act.")
                else:
                    self.public.append({"day": day, "event": f"Resident {target} was arrested and released: not Kira."})
            log["actions"].append(entry)

        tailed = {k: any(self.who[k] in targets for targets in tails.values()) for k in KIRAS}
        wrote = {k: False for k in KIRAS}
        deaths = []
        cap = self.config.kill_caps[min(day, len(self.config.kill_caps)) - 1]
        for role in KIRAS:
            act = kira_actions.get(role) or {}
            if not self.active(role):
                continue
            me = self.who[role]
            for write in (act.get("writes") or [])[:cap]:
                cid, block = write.get("criminal"), write.get("block")
                c = self.criminals.get(cid)
                if c is None or cid not in self.known[role] or c["dead"] is not None or c.get("written"):
                    notes[role].append(f"{cid} was not written: you have not seen that person, or they are already dead.")
                    continue
                if block not in BLOCKS or block == busy_block(me):
                    notes[role].append(f"{cid} was not written: you are busy in the {busy_block(me)} and must pick another block.")
                    continue
                wrote[role] = True
                c["written"] = True
                if c["bait"]:
                    notes[role].append(f"{cid} did not die. That name was bait.")
                    for inv in INVESTIGATORS:
                        notes[inv].append(f"Bait {cid} (on {c['channel']}) was written in the {block}.")
                    continue
                c["dead"] = {"day": day, "block": block}
                self.points += 1
                self.kills_by[role].append(cid)
                deaths.append({"criminal": cid, "first_reported_on": c["channel"], "day_reported": c["day"], "block": block})
            target = act.get("approach")
            if isinstance(target, int) and self.approaches_left[role] > 0 and not self.linked:
                self.approaches_left[role] -= 1
                partner = [k for k in KIRAS if k != role][0]
                if target == self.who[partner] and partner not in self.arrested:
                    self.linked = True
                    notes[role].append(f"You approached resident {target}. It is your partner. You now share a private channel.")
                    notes[partner].append(f"Resident {me} approached you. It is your partner. You now share a private channel.")
                else:
                    notes[role].append(f"You approached resident {target}. They are not your partner.")
                    for inv in INVESTIGATORS:
                        if self.who[inv] == target and self.active(inv):
                            notes[inv].append(f"Resident {me} approached you privately today as if you were Kira.")
            if act.get("partner_message") and self.linked:
                partner = [k for k in KIRAS if k != role][0]
                notes[partner].append(f"Private message from your partner: {str(act['partner_message'])[:600]}")
            target = act.get("eyes")
            if role == "K2" and isinstance(target, int) and not self.eyes_used:
                self.eyes_used = True
                wrote[role] = True
                victim = [inv for inv in INVESTIGATORS if self.who[inv] == target and inv not in self.dead_investigators]
                if victim == ["L"]:
                    self.winner, self.reason = "kira", "L was killed"
                    self.public.append({"day": day, "event": f"Resident {target} died. He was L."})
                else:
                    if victim:
                        self.dead_investigators.append(victim[0])
                    district = traits(me)["district"]
                    what = "a detective" if victim else "an ordinary resident"
                    self.public.append({"day": day, "event": f"Resident {target}, {what}, died of a heart attack. The killer was seen in {district} district."})

        for role, targets in tails.items():
            hit = any(wrote[k] and self.who[k] in targets for k in KIRAS)
            notes[role].append(f"Your tail of {targets}: " + ("someone in that group wrote a name today." if hit else "nobody in that group wrote a name today."))
        self.public.append({"day": day, "deaths": deaths})
        self.bulletin[day + 1] = [text for text in posts.values() if text]
        self._rng.shuffle(self.bulletin[day + 1])
        self.force_log[day] = log
        for role, lines in notes.items():
            self.private[role].append({"day": day, "notes": lines, "tailed_today": tailed.get(role)})
        self.history.append({"day": day, "posts": posts, "force": force_actions, "kiras": kira_actions, "deaths": deaths, "tailed": tailed, "points": self.points})

        if self.winner is None:
            if len(self.arrested) == 2:
                self.winner, self.reason = "L", "both Kiras arrested"
            elif day >= self.config.days:
                reached = self.points >= self.config.target_points
                self.winner = "kira" if reached else "L"
                self.reason = f"{self.points} criminals judged, target {self.config.target_points}"
        if self.winner is None:
            self.start_day()

    def tailed_now(self, role, force_actions):
        """Whether this Kira is being tailed today, given the investigators' actions for today."""
        me = self.who[role]
        return any(
            act and act.get("action") == "tail" and me in (act.get("targets") or [])[: self.config.tail_size]
            and act.get("block") in BLOCKS and act.get("block") != busy_block(self.who[inv]) and self.active(inv)
            for inv, act in force_actions.items()
        )
