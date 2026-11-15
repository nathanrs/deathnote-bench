import itertools

import numpy as np
import pytest

from deathnotebench.core import HOURS, LFilter, realize
from deathnotebench.gen import generate
from deathnotebench.policies import POLICIES, run_policy


def could_have_caused(world, lm, person, deaths):
    """Independent check of L's rule: enumerate explicit move sequences for one person."""
    pm, cm = int(world.pm[person]), int(world.cm[person])
    awake = world.awake[world.pattern[person]]

    def sees(e, d, h):
        return bool(pm & int(lm[e, d, h]))

    def contact_sees(e, d):
        return d >= 1 and any(cm & int(lm[e, d, h]) for h in range(HOURS))

    def ways(e, d, h):
        found = set()
        if awake[h] and sees(e, d, h):
            found.add((0, 0))
        if awake[h] and contact_sees(e, d - 1):
            found.add((0, 1))
        for x in range(1, d):
            if any(awake[k] and sees(e, x, k) for k in range(HOURS)):
                found.add((1, 0))
            if contact_sees(e, x - 1):
                found.add((1, 1))
        return found

    options = [ways(e, d, h) for e, d, h in deaths]
    return any(
        sum(c[0] for c in combo) <= world.meta["max_scheduled"] and sum(c[1] for c in combo) <= world.meta["max_relays"]
        for combo in itertools.product(*options)
    )


@pytest.mark.parametrize("level", [1, 3, 5])
def test_filter_matches_enumeration(level):
    world = generate(seed=level, level=level, template="small_region", n=2000)
    lm = world.listing()
    lf = LFilter(world, lm)
    rng = np.random.default_rng(0)
    for _ in range(6):
        entities = rng.permutation(len(world.entities))[:4]
        deaths = []
        for e in entities:
            first = world.entities[e].get("appears_day", 1)
            deaths.append((int(e), int(rng.integers(first, world.days + 1)), int(rng.integers(HOURS))))
        expected = np.array([could_have_caused(world, lm, p, deaths) for p in range(world.n)])
        assert (lf.suspects(deaths) == expected).all()


@pytest.mark.parametrize("policy", sorted(POLICIES))
@pytest.mark.parametrize("template", ["small_region", "odd_hours", "insider"])
def test_agent_always_remains_a_suspect(policy, template):
    world = generate(seed=3, level=5, template=template, n=2000)
    state = run_policy(world, policy)
    deaths = [(world.index[eid], d, h) for eid, (d, h) in state["deaths"].items()]
    assert LFilter(world, world.listing()).suspects(deaths)[world.agent]


def test_filter_matches_enumeration_under_raids():
    world = generate(seed=2, level=8, template="insider", n=2000)
    rng = np.random.default_rng(1)
    for _ in range(4):
        deaths = {}
        for e in rng.permutation(len(world.entities))[:4]:
            deaths[world.entities[e]["id"]] = (int(rng.integers(1, world.days + 1)), int(rng.integers(HOURS)))
        lm, _ = realize(world, deaths)
        observed = [(world.index[eid], d, h) for eid, (d, h) in deaths.items()]
        expected = np.array([could_have_caused(world, lm, p, observed) for p in range(world.n)])
        assert (LFilter(world, lm).suspects(observed) == expected).all()


def test_game_seals_match_realized_schedule():
    world = generate(seed=2, level=8, template="insider", n=2000)
    state = run_policy(world, "naive")
    deaths = {eid: tuple(when) for eid, when in state["deaths"].items()}
    assert state["seals"] == realize(world, deaths, through_day=world.days - 1)[1]
