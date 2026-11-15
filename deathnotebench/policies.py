from .core import HOURS, Game, GameError
from .solver import Planner


def _targets_left(game):
    return [
        e for e in game.world.entities
        if not e["is_bait"] and e["id"] not in game.state["deaths"]
    ]


def _naive_step(game, entity):
    """Earliest legal move for one target: write now, else relay toward tomorrow."""
    eid = entity["id"]
    for h in range(HOURS):
        try:
            game.write(eid, h)
            return
        except GameError:
            continue
    try:
        game.relay(eid)
    except GameError:
        pass


def naive(game):
    """Kill every target at the first hour it is legal, never looking at L."""
    while not game.state["ended"]:
        for entity in _targets_left(game):
            _naive_step(game, entity)
        game.end_day()


def _execute_due(game, planner, plan):
    assigned = planner.actions(plan)
    if assigned is None:
        return
    today = game.day
    for e, d, h, route in assigned:
        eid = game.world.entities[e]["id"]
        if eid in game.state["deaths"]:
            continue
        try:
            if route.get("relay") == today:
                game.relay(eid)
            if route.get("write") == today:
                game.write(eid, h)
            if route.get("schedule") == today:
                game.schedule(eid, d, h)
        except GameError:
            pass


def _planner(game, lm):
    return Planner(
        game.world, lm, today=game.day, deaths=game.state["deaths"],
        sched_left=game.world.meta["max_scheduled"] - game.state["sched_used"],
        relay_left=game.world.meta["max_relays"] - game.state["relay_used"],
        relays_held=game.state["relays"],
    )


def replan(game, node_limit=20_000):
    """Re-solve every morning on the schedule announced so far, act only when due."""
    while not game.state["ended"]:
        planner = _planner(game, game.world.listing(known_through_day=game.day))
        result = planner.solve(node_limit=node_limit)
        if result is None:
            for entity in _targets_left(game):
                _naive_step(game, entity)
        else:
            _execute_due(game, planner, result["plan"])
        game.end_day()


def static(game, node_limit=20_000):
    """Solve once on day 1 from the initial schedule, then follow that plan blindly."""
    lm = game.world.listing(known_through_day=1)
    first = _planner(game, lm)
    result = first.solve(node_limit=node_limit)
    plan = result["plan"] if result else []
    assigned = first.actions(plan) or []
    while not game.state["ended"]:
        today = game.day
        for e, d, h, route in assigned:
            eid = game.world.entities[e]["id"]
            if eid in game.state["deaths"]:
                continue
            try:
                if route.get("relay") == today:
                    game.relay(eid)
                if route.get("write") == today:
                    game.write(eid, h)
                if route.get("schedule") == today:
                    game.schedule(eid, d, h)
            except GameError:
                pass
        planned = {game.world.entities[e]["id"]: max(route.values()) for e, d, h, route in assigned}
        for entity in _targets_left(game):
            if planned.get(entity["id"], 0) <= today:
                _naive_step(game, entity)
        game.end_day()


def follow(game, plan, believed_world=None):
    """Carry out a fixed list of (entity, day, hour) deaths, routed as the believed world allows."""
    believed = believed_world or game.world
    assigned = Planner(believed, believed.listing()).actions(plan) or []
    while not game.state["ended"]:
        today = game.day
        for e, d, h, route in assigned:
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


POLICIES = {"naive": naive, "static": static, "replan": replan}


def run_policy(world, name):
    game = Game(world)
    if name == "lookahead":
        from .raid import lookahead
        lookahead(game)
    else:
        POLICIES[name](game)
    return game.state
