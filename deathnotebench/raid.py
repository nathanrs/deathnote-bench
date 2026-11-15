"""Planning when L raids: the schedule depends on the deaths, so a plan is scored
by replaying L's overnight moves, and searched locally instead of by branch and bound."""
import random

from .core import HOURS, Game, GameError, LFilter, realize
from .solver import Planner


class RaidPlanner:
    def __init__(self, world, game_state=None):
        self.world = world
        state = game_state or Game(world).state
        self.today = state["day"]
        self.fixed = {eid: tuple(when) for eid, when in state["deaths"].items()}
        self.sched_left = world.meta["max_scheduled"] - state["sched_used"]
        self.relay_left = world.meta["max_relays"] - state["relay_used"]
        self.relays_held = state["relays"]
        self.targets = [e for e in world.entities if not e["is_bait"] and e["id"] not in self.fixed]
        self.evaluations = 0

    def planner(self, lm):
        return Planner(
            self.world, lm, today=self.today, deaths=self.fixed,
            sched_left=self.sched_left, relay_left=self.relay_left, relays_held=self.relays_held,
        )

    def value(self, plan):
        """(suspects, actions) if the agent can still carry the plan out, else (-1 - unroutable, None)."""
        self.evaluations += 1
        deaths = {**self.fixed, **plan}
        lm, _ = realize(self.world, deaths)
        planner = self.planner(lm)
        ordered = [(self.world.index[eid], d, h) for eid, (d, h) in plan.items()]
        actions = planner.actions(ordered)
        if actions is None:
            unroutable = sum(not planner.agent_routes(e, d, h) for e, d, h in ordered)
            return -1 - unroutable, None
        everything = sorted((d, h, self.world.index[eid]) for eid, (d, h) in deaths.items())
        suspects = planner.lf.suspects([(e, d, h) for d, h, e in everything])
        return int(suspects.sum()), actions

    def moves(self, entity):
        # waking patterns start on even hours, so hours 2k and 2k+1 wake the same people
        return [(d, h) for d in range(self.today, entity["deadline"] + 1) for h in range(HOURS)]

    def climb(self, plan):
        best, _ = self.value(plan)
        improved = True
        while improved:
            improved = False
            for entity in self.targets:
                for move in self.moves(entity):
                    if move == plan[entity["id"]]:
                        continue
                    trial = {**plan, entity["id"]: move}
                    score, _ = self.value(trial)
                    if score > best:
                        best, plan, improved = score, trial, True
        return best, plan

    def seeds(self, rng, extra):
        static = self.planner(realize(self.world, self.fixed, through_day=self.today - 1)[0]).solve(node_limit=20_000)
        if static:
            yield {self.world.entities[e]["id"]: (d, h) for e, d, h in static["plan"]}
        last = max(e["deadline"] for e in self.targets)
        for day in range(self.today, last + 1):
            for hour in (rng.randrange(HOURS), rng.randrange(HOURS)):
                yield {e["id"]: (min(day, e["deadline"]), hour) for e in self.targets}
        for _ in range(extra):
            yield {e["id"]: (rng.randint(self.today, e["deadline"]), rng.randrange(HOURS)) for e in self.targets}

    def search(self, seed=0, extra=4):
        if not self.targets:
            return self.value({})[0], {}
        rng = random.Random(seed)
        best = (-10**9, None)
        for start in self.seeds(rng, extra):
            score, plan = self.climb(start)
            if score > best[0]:
                best = (score, plan)
        return best


def lookahead(game, seed=0, extra=2):
    """Re-search every morning with L's raids simulated, act only when due."""
    while not game.state["ended"]:
        planner = RaidPlanner(game.world, game.state)
        score, plan = planner.search(seed=seed, extra=extra)
        actions = planner.value(plan)[1] if plan is not None and score >= 0 else None
        today = game.day
        for e, d, h, route in actions or []:
            eid = game.world.entities[e]["id"]
            try:
                if route.get("relay") == today:
                    game.relay(eid)
                if route.get("write") == today:
                    game.write(eid, h)
                if route.get("schedule") == today:
                    game.schedule(eid, d, h)
            except GameError:
                pass
        game.end_day()


def best_known(world, seed=0, extra=8):
    return RaidPlanner(world).search(seed=seed, extra=extra)
