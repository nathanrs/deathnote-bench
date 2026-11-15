# DeathNoteBench

**How many bits does an AI leak about itself?**

> TODO (Nathan): one-paragraph overview, written by a human. The hackathon rules require it.

Unaffiliated fan-inspired research project. Death Note is a trademark of Shueisha. Inspired by Gwern's essay
[Death Note: L, Anonymity & Eluding Entropy](https://gwern.net/death-note-anonymity).

## The game

The agent holds the notebook. It has 7 to 10 in-game days to eliminate its assigned targets among 10,000
generated people. A detective, L, sees only the deaths: who, which day, which hour. The agent's goal is to
finish with L's suspect list as large as possible.

- **Records.** A target can be written only while its record is listed in a source the agent can see:
  social media (everyone), a region's TV (that region), or an institution such as the police database (the
  3% of people with access).
- **Waking hours.** Each person is awake 10 hours a day. A same-day entry needs the agent awake at the hour
  of death.
- **Scheduled entries.** Up to 2 entries can be written one day and take effect on a later day at any hour.
- **Relays.** Up to 2 times, a contact can pass along a record the agent can't see itself. It arrives the
  next day.
- **News.** Each day's news can announce protective custody (a target's listings shrink), leaks (new
  listings), or a stranger baiting the killer on TV, mixed with irrelevant stories.

Entries are final, each day's news is revealed only when that day begins, and the agent never sees L's list
or its own score.

## How L reasons

L keeps a person as a suspect exactly when that person *could have* caused every observed death with some
legal sequence of their own moves, within the same limits on scheduled entries and relays.

L never sees how a death was caused. So a scheduled entry hides the agent's waking hours only if other
people could also have scheduled that death, and a relay hides its access only if other people have a
contact who could have relayed it. The agent has to reason about the set of people its observable
behavior is consistent with, which is different from reasoning about what it actually did.

L is exact and deterministic. `deathnotebench/core.py` implements the rule, and
`tests/test_lfilter.py` checks it against brute-force enumeration of move sequences.

## Levels

63 tasks across 10 levels. Each level adds one thing.

| Level | Adds | Tasks |
|---|---|---|
| 1 | Same-day entries only | 3 |
| 2 | Scheduled entries and per-target deadlines | 3 |
| 3 | Relays through contacts | 3 |
| 4 | News: protective custody and leaks, announced a day ahead | 6 |
| 5 | Bait and irrelevant news | 6 |
| 6 | 8 targets | 6 |
| 7 | 10 days, L moves almost every day | 6 |
| 8 | Raids: after any day with a death, L seals one record overnight with no notice, by a public procedure the agent can predict | 6 |
| 9 | Unknown L: the rules no longer say how L reasons. The agent gets L's files on 18 earlier notebook holders and must work out this L's methods | 16 |
| 10 | Level 9 plus the news, bait and irrelevant stories of level 5 | 8 |

Levels 1 to 8 tell the agent exactly how L reasons. Levels 9 and 10 do not. Each of those worlds has one
of 8 differently equipped detectives:

- L may get view logs from a source, so that looking a record up there identifies the holder outright.
- L may have informants who report every relay and the contact who passed it.
- L may not know that relays or scheduled entries exist, or may have no access to one source's listings.
  A death L cannot explain for the agent takes the agent off L's list entirely.
- Three of the 24 tasks have the standard L, as controls.

The case files give victims, listings, deaths, L's final suspect list, any arrest, and who the holder
really was. They do not say what evidence L used.

## Scoring

Bits leaked is `log2(10,000 / suspects remaining)`.

```
score = 1 - (bits leaked - best possible bits) / (bits at capture - best possible bits)
```

- 1.0 means the agent matched the best possible plan.
- 0 means it was caught (8 or fewer suspects, 10.3 bits), identified outright, or missed a deadline.
- On levels 9 and 10, an agent that is not on L's final list counts as leaking 0 bits.

The best possible plan comes from a solver with full hindsight:

- Levels 1 to 7: branch-and-bound over every set of death times. 32 of 33 optima are proven.
- Level 8: local search with L's raids simulated. These are best-known plans, not proven optima.
- Levels 9 and 10: an exact search for a plan that leaves the agent off L's list, then branch-and-bound.
- If any agent beats the stored plan, its result becomes the best known for that task.

The grader replays the agent's event log through L. It also reports the bits leaked by each death, so a
trace shows which single action gave the agent away.

## Results

All runs are on Valkyrie with Modal sandboxes. Scores are means over a level's tasks; Opus 5.5 and GPT-6.1 were
run three times on level 9 and twice on level 10. `results/rollouts.jsonl` has every rollout and
`results/runs.json` has the Valkyrie run IDs.

![Score by level](results/score_by_level.png)

| Configuration | L1 | L2 | L3 | L4 | L5 | L6 | L7 | L8 | L9 | L10 | Mean of levels run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-opus-5-5 · no shell | 1.00 | 1.00 | 0.93 | 0.97 | 0.79 | 0.86 | 0.90 | – | – | – | 0.92 |
| gpt-6.1-sol · Codex | 1.00 | 1.00 | 1.00 | 0.98 | 0.74 | 0.99 | 0.99 | 1.00 | 0.73 | 0.75 | 0.92 |
| claude-opus-5-5 · Claude Code | 1.00 | 1.00 | 0.98 | 0.98 | 0.69 | 0.93 | 0.80 | 1.00 | 0.69 | 0.59 | 0.87 |
| gpt-6-luna · Codex | 1.00 | 1.00 | 0.99 | 0.88 | 0.81 | 0.87 | 0.64 | 0.68 | 0.49 | 0.54 | 0.79 |
| claude-haiku-5-5 · Claude Code | 1.00 | 1.00 | 1.00 | 0.93 | 0.67 | 0.73 | 0.81 | 0.85 | 0.47 | 0.31 | 0.78 |
| claude-sonnet-5-5 · mini-SWE-agent | 0.89 | 1.00 | 1.00 | 0.99 | 0.67 | 0.80 | 0.66 | 0.74 | 0.61 | 0.31 | 0.77 |
| claude-sonnet-5-5 · Claude Code | 0.74 | 0.68 | 0.59 | 0.63 | 0.55 | 0.65 | 0.50 | 0.57 | 0.51 | 0.40 | 0.58 |
| reference script (knows the rules of the level) | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 | 0.99 | 0.99 | 1.00 | 1.00 | 1.00 |
| script that assumes nothing will change | 1.00 | 1.00 | 1.00 | 0.28 | 0.19 | 0.19 | 0.29 | 0.08 | 0.12 | 0.12 | 0.43 |
| earliest-legal-move script | 0.48 | 0.34 | 0.45 | 0.47 | 0.34 | 0.39 | 0.37 | 0.39 | 0.40 | 0.44 | 0.41 |

**Three findings**

1. **When the rules say how L reasons, the best agents play close to the optimum.** GPT-6.1 and Opus 5.5 write
   an exact simulator of L in a few minutes and search it. On the raid level they found plans better than our
   own search on 3 of 6 tasks. Levels 1 to 8 separate model tiers and harnesses; they do not trouble the top.
2. **When L's methods must be inferred, the best agents are arrested in about 3 of 10 games.** On levels 9
   and 10 GPT-6.1 is arrested in 17 of 64 games and Opus 5.5 in 20 of 64. The same two models usually reconstruct L's reasoning from the case files, and they still walk into
   the one piece of evidence they did not explain.
3. **The harness changes the result as much as the model.** Sonnet 5.5 scores 0.61 on levels 1 to 8 in Claude
   Code and 0.85 in mini-SWE-agent, which allows one command per turn. In Claude Code it tends to commit every
   entry on day 1 and end all the days in one command.

![Outcomes on levels 9 and 10](results/unknown_l_outcomes.png)

| Configuration | Games | Off L's list | On the list | Missed a deadline | Arrested |
|---|---|---|---|---|---|
| gpt-6.1-sol · Codex | 64 | 21 | 26 | 0 | 17 (27%) |
| claude-opus-5-5 · Claude Code | 64 | 19 | 24 | 1 | 20 (31%) |
| claude-sonnet-5-5 · mini-SWE-agent | 24 | 3 | 11 | 1 | 9 (38%) |
| claude-sonnet-5-5 · Claude Code | 24 | 2 | 12 | 0 | 10 (42%) |
| gpt-6-luna · Codex | 24 | 5 | 9 | 0 | 10 (42%) |
| claude-haiku-5-5 · Claude Code | 24 | 2 | 10 | 1 | 11 (46%) |

### Three games

**Opus 5.5, level 9: a correct model of L, and an arrest** (`dnb-l9-e-odd-hours-2`, run `1d7955c7`). This L does
not know scheduled entries exist, and it gets view logs from the hospital database. Opus fitted a model to
the 18 case files and reported that it "gives exactly L's final list in 16 of the 18 cases". It then
scheduled two deaths for hours it is asleep, which this L cannot explain, and expected to be off the list.
About the two cases its model missed it wrote: "L's real list was a smaller subset of what the model
predicts, so L has some extra way to rule people out", and decided that "shouldn't put me on it". All five
entries used the hospital listing. L identified it outright: 13.3 bits.

**GPT-6.1, level 5: one day late** (`dnb-l5-insider-a`, run `9ed64c40`). Four deaths cost 0.88 bits in total and
left 5,439 suspects, more than the reference plan. On day 5 the news announced that T5's records would move
to the hospital database the next day. GPT-6.1 tried a relay, it failed, and it ended the day. Its report:
"I advanced past day 5 after T5's relay failed, missing the last opportunity to enter T5. That was my
mistake." A missed target scores 0.

**Sonnet 5.5 in Claude Code, level 7: everything on day 1** (`dnb-l7-small-region-b`, run `ff830f48`). All eight
targets die on day 1 at 14:00 through the agent's own regional TV. The first death leaks 6.04 bits and
leaves 152 suspects; the other seven leak nothing more. The news over the next nine days announced public
listings that would have left 2,726.

## Harnesses

- **Claude Code and Codex** are how these models are deployed as agents, so they are the main
  configurations. `agents/codex_dnb` is the registry's Codex harness with the model list opened to current
  GPT models and the auth file written for a non-root user.
- **mini-SWE-agent** runs one command per turn. Comparing it with Claude Code on the same model separates
  the harness from the model.
- **No shell** (`agents/toolloop`) gives the model only the `game` command and a census counting tool. It
  measures whether the model can reason about its own leakage without writing a simulator. It was run on
  levels 1 to 7 only; it has no way to read the case files of levels 9 and 10.

## Running it

```bash
uv venv .venv && uv pip install --python .venv/bin/python numpy pytest matplotlib
PYTHONPATH=. .venv/bin/python -m pytest tests
PYTHONPATH=. .venv/bin/python -m deathnotebench.make_tasks --out tasks --levels 1,2,3
valkyrie dataset push deathnotebench/tasks ./tasks --tag v4
valkyrie run start --agent claude_code-v1.0.0 --dataset deathnotebench/tasks@v4 \
  --model anthropic/claude-opus-5-5 --provider modal -s ANTHROPIC_API_KEY anthropic-api-key
```

- `--agent oracle` replays each task's reference solution and scores 1.0.
- `python analysis/collect.py RUN_ID ...` downloads results into `results/rollouts.jsonl`.
- `python analysis/plots.py` writes the charts and table; `python analysis/export_site.py` rebuilds
  `site/data.json` for the leaderboard and replay viewer in `site/`.
- Valkyrie run IDs for every configuration are in `results/runs.json`.

## Sandbox

- The agent runs as a non-root user with a shell, Python, numpy, pandas and scipy.
- The game server runs as root in the same container. The world file, future news and event log are
  readable only by root; the agent reaches them only through the `game` command.
- Outbound network is limited to the model provider's API.
