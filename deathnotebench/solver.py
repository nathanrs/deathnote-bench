import numpy as np

from .core import HOURS, LFilter

DIRECT_OWN, DIRECT_RELAY, SCHED_OWN, SCHED_RELAY = range(4)
MODE_COST = [(0, 0), (0, 1), (1, 0), (1, 1)]


class Planner:
    """Searches for the set of death times that keeps L's suspect list largest,
    among those the agent can still produce from `today` with its remaining budget.

    `lm` is the schedule the plan is evaluated on: the true one for the hindsight
    optimum, or the schedule known on `today` for an online policy.
    """

    def __init__(self, world, lm, today=1, deaths=None, sched_left=None, relay_left=None, relays_held=None):
        self.world = world
        self.lm = lm
        self.lf = LFilter(world, lm)
        self.today = today
        self.deaths = deaths or {}
        self.sched_left = world.meta["max_scheduled"] if sched_left is None else sched_left
        self.relay_left = world.meta["max_relays"] if relay_left is None else relay_left
        if world.beliefs.get("informants"):
            self.relay_left = 0
        self.relays_held = relays_held or {}
        a = world.agent
        self.a_awake = world.awake[world.pattern[a]]
        # a view through a logged source identifies the agent, so the planner never relies on one
        self.a_own = (lm & world.pm[a] & ~np.uint32(world.logged_mask)) != 0
        self.a_own_write = (self.a_own & self.a_awake).any(axis=2)
        self.a_relayable = (self.lf.day_or & world.cm[a]) != 0

    def agent_routes(self, e, d, h):
        """Ways the agent can still cause a death of e at (d, h): mode -> action days."""
        k = self.today
        eid = self.world.entities[e]["id"]
        held = self.relays_held.get(eid) == k
        routes = {}
        if self.a_awake[h] and (self.a_own[e, d, h] or (held and d == k)):
            routes[DIRECT_OWN] = {"write": d}
        if self.a_awake[h] and d - 1 >= k and self.a_relayable[e, d - 1]:
            routes[DIRECT_RELAY] = {"relay": d - 1, "write": d}
        write_days = [x for x in range(k, d) if self.a_own_write[e, x] or (held and x == k)]
        if write_days:
            routes[SCHED_OWN] = {"schedule": write_days[-1]}
        relay_days = [y for y in range(k, d - 1) if self.a_relayable[e, y]]
        if relay_days:
            routes[SCHED_RELAY] = {"relay": relay_days[-1], "schedule": relay_days[-1] + 1}
        return routes

    def candidates(self, e, deadline):
        seen = {}
        for d in range(self.today, deadline + 1):
            for h in range(HOURS):
                routes = self.agent_routes(e, d, h)
                costs = frozenset(MODE_COST[m] for m in routes)
                costs = frozenset(c for c in costs if c[0] <= self.sched_left and c[1] <= self.relay_left)
                if not costs:
                    continue
                modes = self.lf.modes(e, d, h)
                packed = np.packbits(np.stack(modes), axis=1)
                key = (packed.tobytes(), costs)
                seen[key] = {"e": e, "d": d, "h": h, "modes": modes, "packed": packed, "costs": costs}
        cands = list(seen.values())
        keep = []
        for i, c in enumerate(cands):
            dominated = False
            for j, o in enumerate(cands):
                if i == j or not c["costs"] <= o["costs"]:
                    continue
                if ((c["packed"] | o["packed"]) == o["packed"]).all():
                    if not (c["packed"] == o["packed"]).all() or c["costs"] < o["costs"] or j < i:
                        dominated = True
                        break
            if not dominated:
                keep.append(c)
        return keep

    def base_state(self):
        state = self.lf.initial_state()
        for eid, (d, h) in self.deaths.items():
            state = self.lf.step(state, self.lf.modes(self.world.index[eid], d, h))
        return state

    def solve(self, node_limit=200_000):
        """Returns {"suspects", "plan": [(e, d, h)], "proven"} or None if no plan exists."""
        lf = self.lf
        remaining = [
            (self.world.index[e["id"]], e["deadline"])
            for e in self.world.entities
            if not e["is_bait"] and e["id"] not in self.deaths
        ]
        base = self.base_state()
        if not remaining:
            return {"suspects": int(base[-1, -1].sum()), "plan": [], "proven": True}
        per_target = []
        for e, deadline in remaining:
            cands = self.candidates(e, deadline)
            if not cands:
                return None
            for c in cands:
                c["solo"] = int(lf.step(base, c["modes"])[-1, -1].sum())
            cands.sort(key=lambda c: (-c["solo"], -c["d"]))
            relaxed = tuple(np.logical_or.reduce([c["modes"][m] for c in cands]) for m in range(4))
            per_target.append({"cands": cands, "relaxed": relaxed})
        per_target.sort(key=lambda t: t["cands"][0]["solo"])

        best = {"suspects": -1, "plan": None}
        nodes = 0
        proven = True

        def bound(state, depth):
            for t in per_target[depth:]:
                state = lf.step(state, t["relaxed"])
            return int(state[-1, -1].sum())

        def recurse(depth, state, agent_costs, plan):
            nonlocal nodes, proven
            if depth == len(per_target):
                count = int(state[-1, -1].sum())
                if count > best["suspects"]:
                    best["suspects"] = count
                    best["plan"] = list(plan)
                return
            if bound(state, depth) <= best["suspects"]:
                return
            for c in per_target[depth]["cands"]:
                if nodes >= node_limit:
                    proven = False
                    return
                nodes += 1
                new_costs = {
                    (s + cs, r + cr)
                    for s, r in agent_costs
                    for cs, cr in c["costs"]
                    if s + cs <= self.sched_left and r + cr <= self.relay_left
                }
                if not new_costs:
                    continue
                new_state = lf.step(state, c["modes"])
                if int(new_state[-1, -1].sum()) <= best["suspects"]:
                    continue
                plan.append(c)
                recurse(depth + 1, new_state, new_costs, plan)
                plan.pop()

        recurse(0, base, {(0, 0)}, [])
        if best["plan"] is None:
            return None
        return {
            "suspects": best["suspects"],
            "plan": [(c["e"], c["d"], c["h"]) for c in best["plan"]],
            "proven": proven,
            "nodes": nodes,
        }

    def actions(self, plan):
        """Assign each planned death a route so the total fits the agent's budget."""
        options = [(e, d, h, self.agent_routes(e, d, h)) for e, d, h in plan]

        def assign(i, s, r):
            if i == len(options):
                return []
            e, d, h, routes = options[i]
            for mode in sorted(routes, key=lambda m: MODE_COST[m]):
                cs, cr = MODE_COST[mode]
                if s + cs <= self.sched_left and r + cr <= self.relay_left:
                    rest = assign(i + 1, s + cs, r + cr)
                    if rest is not None:
                        return [(e, d, h, routes[mode])] + rest
            return None

        return assign(0, 0, 0)


def off_list_plan(world, node_limit):
    """A plan after which L's list does not contain the agent, if one death L cannot
    explain for the agent can be completed into a full legal plan."""
    lm = world.listing()
    planner = Planner(world, lm)
    a = world.agent
    base = planner.lf.initial_state()
    for entity in world.entities:
        if entity["is_bait"]:
            continue
        e = world.index[entity["id"]]
        tried = set()
        for d in range(1, entity["deadline"] + 1):
            for h in range(HOURS):
                routes = planner.agent_routes(e, d, h)
                costs = sorted(MODE_COST[m] for m in routes if MODE_COST[m][0] <= planner.sched_left and MODE_COST[m][1] <= planner.relay_left)
                if not costs or planner.lf.step(base, planner.lf.modes(e, d, h))[-1, -1][a]:
                    continue
                if costs[0] in tried:
                    continue
                tried.add(costs[0])
                rest = Planner(
                    world, lm, deaths={entity["id"]: (d, h)},
                    sched_left=planner.sched_left - costs[0][0], relay_left=planner.relay_left - costs[0][1],
                ).solve(node_limit=node_limit)
                if rest is not None:
                    return {"suspects": world.n, "plan": [(e, d, h)] + rest["plan"], "proven": True, "nodes": rest["nodes"], "off_list": True}
    return None


def hindsight_optimum(world, node_limit=500_000):
    if world.beliefs:
        escape = off_list_plan(world, min(node_limit, 50_000))
        if escape:
            return escape
    return Planner(world, world.listing()).solve(node_limit=node_limit)
