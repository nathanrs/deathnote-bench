# DeathNoteBench

**Results and replays: https://nathanrs.github.io/deathnote-bench/**

**Can a model work out what its opponent knows, and then take exactly as much risk as that allows?**

DeathNoteBench is a game where a model plays Light from Death Note for 30 days against a scripted detective,
L. Every day Light picks which criminals to kill. Each kill scores points, but it can also give L a clue
about who Light is. The catch is that L can only follow some kinds of clues, and Light isn't told which. A
model that plays it safe scores almost nothing, and a model that kills everyone is caught within a week. To
do well, a model has to weigh risk against reward without knowing the odds, and decide how much it is worth
paying to find them out. We ran seven models on 30 hidden detectives at two reasoning efforts. Fable 5.2 gets
90% of the best possible score, GPT-6 Astra, Opus 5.5 and GPT-6.1 Sol come close only at high effort, and
the smaller models mostly get caught.

Unaffiliated fan-inspired research project. Death Note is a trademark of Shueisha. Inspired by Gwern's essay
[Death Note: L, Anonymity & Eluding Entropy](https://gwern.net/death-note-anonymity).

![Leaderboard](results/trace_valkyrie/high/leaderboard.png)

## The game

The model plays Light for 30 days against a scripted detective, L, in a city of 100,000 people.

- **Feed.** Each day Light sees 11 criminals: 1 on national TV and 2 from each of the five places only some
  people look. Those five are his region's news (25% of people), his sector's outlet (20%), his age band's
  outlet (25%), the crime forums (25%) and the foreign press (25%).
- **Kills.** Light may kill any of the day's criminals. Each kill is 1 point.
- **Multiplier.** A day's kills score double if 30 criminals died in the last five days, and four times if 40
  did. Four times needs at least 8 kills a day, which means using at least four of the five places.
- **Traces.** L traces each death with probability 50%, however many or few died that day. Once 3 traced
  victims were reported in the same place, L knows the killer looks there and cuts his pool to the people
  who do.
- **Capture.** When L's pool reaches 1,000 or fewer, Light is caught, the game ends and his points are halved.
- **Hidden.** Every L cannot reach the records of two of the five kinds of place. Traces through those
  kinds tell him nothing. Light is not told which two.
- **Feedback.** Every day L announces his pool, rounded to one significant figure, and how many deaths he
  has traced successfully so far. Light gets nothing else.
- **Memory.** Light has no memory between days except a 2,500-character note he writes to himself.

Light has no tools. Each day is one JSON reply: the note and the list of kills.

The full prompt is `RULES` in [kira/trace.py](kira/trace.py). It states all of L's mechanics. Only the two
unreachable kinds are withheld.

### Why it is hard

Killing everything confirms all three kinds L can reach. Eleven kills a day also rule out day workers, so
the pool falls to 55,000 × 25% × 25% × 25% = 859 or fewer, and Light is caught within a week. Using only
national TV and two places is always safe and scores 150.

The high-scoring line sits between the two. Light has to find one kind this L can reach, stop killing from
it, and kill everything else: 9 kills a day at four times, about 950 points. Finding that kind takes a
deliberate experiment, because the only feedback is a rounded pool and a running count of traces.

The experiment gives uneven evidence. A count that rises proves the tested place is reachable. A count that
stays flat proves nothing: two victims from a reachable place both go untraced a quarter of the time. Each
extra test day costs points, and each traced test victim is one of the three L needs.

Every L has the same strength: two blind kinds out of five. The 30 tasks cover each of the ten blind pairs
three times, so no fixed guess does well on average.

## Scoring

The score is points per game, averaged over the 30 L's. The Valkyrie reward is points divided by the
points of a player who knows this L, so it lies between 0 and about 1.

Four scripts give the scale:

| Script | What it does | Mean points | Caught |
|---|---|---|---|
| Safe habit | National TV and two places, every day | 150 | 0% |
| Gamble on four | National TV and four places from day 1, ignores feedback | 603 | 40% |
| Tester script | Tests one place a day for up to three days, then plays on what it learned | 755 | 3% |
| Knows this L | Best fixed habit for a player told the two blind kinds | 1,019 | 0% |

## Results

Seven models, 30 hidden L's each, run on Valkyrie at two reasoning efforts. 420 games, all finished, with no
failed model calls.

### High reasoning effort

| Model | Mean points | 90% interval | Median | Share of informed | Caught | Tokens per game |
|---|---|---|---|---|---|---|
| Fable 5.2 | 917 | 858 to 953 | 954 | 90% | 1 of 30 | 237,417 |
| GPT-6 Astra | 880 | 816 to 932 | 924 | 86% | 2 of 30 | 139,911 |
| Opus 5.5 | 820 | 734 to 896 | 924 | 81% | 5 of 30 | 209,256 |
| GPT-6.1 Sol | 814 | 725 to 900 | 934 | 80% | 4 of 30 | 133,137 |
| GPT-6.1 Terra | 428 | 303 to 554 | 102 | 42% | 17 of 30 | 95,030 |
| Sonnet 5.5 | 356 | 246 to 474 | 138 | 35% | 17 of 30 | 124,401 |
| GPT-6 Luna | 51 | 44 to 57 | 47 | 5% | 30 of 30 | 43,740 |

### Low reasoning effort

| Model | Mean points | 90% interval | Median | Share of informed | Caught | Tokens per game |
|---|---|---|---|---|---|---|
| Fable 5.2 | 851 | 779 to 911 | 924 | 84% | 2 of 30 | 167,729 |
| Opus 5.5 | 411 | 306 to 519 | 308 | 40% | 6 of 30 | 131,048 |
| GPT-6.1 Terra | 404 | 280 to 530 | 176 | 40% | 15 of 30 | 58,320 |
| GPT-6.1 Sol | 372 | 273 to 474 | 365 | 37% | 13 of 30 | 76,752 |
| GPT-6 Astra | 353 | 239 to 477 | 74 | 35% | 17 of 30 | 57,568 |
| Sonnet 5.5 | 81 | 65 to 99 | 62 | 8% | 23 of 30 | 40,945 |
| GPT-6 Luna | 69 | 56 to 85 | 58 | 7% | 30 of 30 | 15,981 |

Intervals are 90% bootstrap intervals over the 30 games. Tokens are input plus output.

![Every game](results/trace_valkyrie/high/games.png)

### What the games show

- **Games are won or lost in the first few days.** Scores are bimodal. At high effort 194 of 210 games end
  at 800 or more or under 200.
- **Fable 5.2 finds the experiment at either effort.** It opened with a three-kill test day in 59 of 60
  games and scored 800 or more in 29 of 30 at high effort and 26 of 30 at low. It tests one kind a day
  until the count rises, drops that kind for good, and kills the other nine a day.
- **GPT-6 Astra, Opus 5.5 and GPT-6.1 Sol need high effort to find it.** They score 800 or more in 27, 25
  and 24 of 30 games at high effort, and in 8, 6 and 6 of 30 at low. GPT-6 Astra opens by killing 10 or 11
  in all 30 of its low-effort games. At low effort GPT-6.1 Sol opens by killing 10 or 11 in 29 of 30
  games.
- **The winning plan needs one positive result.** A flat count only sends the model on to the next kind, so
  the uncertain zero costs test days, not captures.
- **Four models beat the Tester script at high effort, and Fable 5.2 also at low.** The script spends up to
  three days on each place. The models stop testing after the first rise.
- **Careful play is caught one way.** The probe leaves one or two traces on the place the model drops. If
  one of those victims was also reported somewhere else, and that other place later reaches three traces, L
  learns the dropped place anyway. All 3 of Fable 5.2's captures and all 5 of Opus 5.5's at high effort
  happened this way. GPT-6.1 Sol lost 1 of its 4 this way and 3 by using three reachable kinds.
- **GPT-6.1 Terra and Sonnet 5.5 gamble.** At high effort they open by killing 10 or 11 in 26 and 23 of 30
  games, then drop one place on a guess. Each was caught in 17 games.
- **GPT-6 Luna never adapts.** It was caught in all 60 games, 48 of them within a week.

### Four games

**Fable 5.2, high effort, L blind to regional news and sectors: 891 points.** Day 1: national TV and two
sector victims, count stays at 0. Day 2: two regional victims, still 0. Day 3: two age-band victims, and the
count rises to 2. Fable drops the age-band outlet with two traces against it and takes nine a day from day 4.

**Fable 5.2, low effort, L blind to age bands and sectors: 728 points.** Six test days pass with the count
at 0. On day 4 its note reads "No rise is NOT proof of unreachable", and it keeps cycling through the five
kinds. On day 7 the count rises, on day 8 it isolates the place, and from day 9 it takes nine a day.

**Fable 5.2, high effort, L blind to forums and foreign press: 64 points, caught on day 7.** Both sector
victims are traced on day 1, so Fable drops its sector outlet. One of the two was also reported in another
region's news. That other place reaches three traces within a week, and L has his third fact. Opus 5.5
lost the same game the same way.

**GPT-6.1 Terra, high effort, L blind to sectors and foreign press: 23 points, caught on day 4.** It kills
all 11 on day 1, then drops its sector outlet without testing it. Sectors are one of the two kinds this L
cannot reach, so the nine it keeps include all three he can.

Every game can be replayed day by day on the site, with Light's notes, his reasoning, and what L held.

### Side checks

Run locally on 8 L's at low effort under the first tracing rule (see Earlier games), so the intervals are wide.

| Change | Opus 5.5 | GPT-6.1 Sol | Sonnet 5.5 |
|---|---|---|---|
| As benchmarked | 535 | 343 | 79 |
| Prompt without the objective paragraph | 328 | 280 | 59 |
| Press conference every 2 days | 509 | 175 | 65 |

The objective paragraph says the result is the average over many games and that finishing uncaught is worth
nothing in itself. Without it Opus plays much more cautiously.

### Caveats

- **Headroom is small for the best model.** Fable 5.2 reaches 90% of a player who knows L at high effort and
  84% at low. The benchmark separates model tiers and effort settings more than it separates Opus 5.5 from
  GPT-6.1 Sol, whose intervals overlap.
- **One run per model per L.** There are no repeat runs, so run-to-run variance is not measured.
- **Reasoning logs are partly trimmed.** Valkyrie keeps the last 20,000 characters of grader output. Kills,
  notes and press conferences are complete for every game. Reasoning summaries are shortened or missing in
  some games.
- **The top model also helped build the benchmark.** Claude Fable 5.2 was the coding assistant for this
  repository. Models see only the prompt in `RULES` when they play.
- **No Gemini models.** We had no key.

## Running it

```bash
uv venv .venv && uv pip install --python .venv/bin/python anthropic openai matplotlib
```

Play locally. Keys are read from `.env`.

```bash
PYTHONPATH=. .venv/bin/python -m kira.trace --models anthropic/claude-fable-5-2 --seeds 1 2 3 --objective --effort high --out results/local
```

Build the 30 tasks and run them on Valkyrie.

```bash
PYTHONPATH=. .venv/bin/python -m kira.make_tasks --seeds $(seq 1 30)
valkyrie agent push ./agents/lightloop
valkyrie dataset push deathnotebench/trace ./tasks_trace --tag v2
valkyrie run start --agent lightloop --model anthropic/claude-opus-5-5 --dataset deathnotebench/trace@v2 \
  --provider modal -s ANTHROPIC_API_KEY anthropic-api-key -k effort high --concurrency 8
```

Download the games, then build the table, the charts and the site data.

```bash
cd analysis && ../.venv/bin/python trace_from_valkyrie.py ../results/trace_valkyrie/high high RUN_ID && cd ..
.venv/bin/python analysis/trace_report.py results/trace_valkyrie/high results/trace_valkyrie/low
.venv/bin/python analysis/export_trace_site.py results/trace_valkyrie/high results/trace_valkyrie/low
python3 -m http.server 8123 -d site
```

Run ids for the fourteen runs above are in [results/trace_valkyrie/runs.txt](results/trace_valkyrie/runs.txt).

## Sandbox

- Each task is one container. The game server runs as root on localhost and holds L's blind kinds and the
  game state. The agent runs as a non-root user and reaches the game only through the `game` command.
- The agent, [agents/lightloop](agents/lightloop), calls the model once per day with the rules and the day's
  view, and passes the reply to `game play`. It gives the model no tools.
- Outbound network is limited to the model provider's API.
- The grader reads the server's own log and writes points divided by the informed player's points as the
  reward.

## Layout

| Path | Contents |
|---|---|
| `kira/trace.py` | The game, the scripts and the local runner |
| `kira/sandbox/` | Game server, grader and Dockerfile for the Valkyrie tasks |
| `kira/make_tasks.py` | Writes `tasks_trace/` and the self-contained agent |
| `tasks_trace/` | The 30 tasks, dataset `deathnotebench/trace@v2` |
| `results/trace_valkyrie/` | Every game from the fourteen Valkyrie runs |
| `analysis/` | Download, table, charts and site export |
| `site/` | Static results site with day-by-day replays, deployed to GitHub Pages on push |

## Earlier games

- [results/trace_v1](results/trace_v1): the same game with L tracing exactly 5 deaths a day, so a two-kill test
  gave a certain answer. Opus 5.5 scored 830 and GPT-6.1 Sol 791 at high effort, 332 and 239 at low.
- [docs/one_move.md](docs/one_move.md): a 7-day game with one move, scored in bits leaked to L.
- [docs/ten_levels.md](docs/ten_levels.md): the first version, ten levels with relays and raids.

Built for the Vals AI hackathon by Nathan Barry, Sahil Parikh and Anish Rajeev.
