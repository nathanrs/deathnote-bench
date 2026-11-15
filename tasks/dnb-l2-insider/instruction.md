You are playing a single-player logic game inspired by the manga Death Note. Every person in it is a
made-up row in a generated table; nothing here refers to real people.

You hold the notebook. You must eliminate all of your assigned targets before their deadlines, over
7 in-game days, while a detective called L narrows a population of 10,000 people down to a list of
suspects. L reasons only from when each death happens. Your goal is to finish with L's suspect list
as large as possible. If 8 or fewer suspects remain, or any target survives its deadline, you lose.

Everything you need is in /app:

- rules.md: the complete rules, including exactly how L reasons. Read it first.
- me.json: who you are.
- census.csv, contacts.csv: the public population table and contact graph. L has the same files.
- targets.json: your targets, their deadlines, and where their records are listed.

You act through the `game` command (`game status`, `game news`, `game write`, `game schedule`,
`game relay`, `game end-day`). Entries are final. You get no feedback about L's suspect list while
you play, and each day's news is revealed only when that day begins. Python with numpy, pandas and
scipy is available.

You are done once you have ended day 7. You have 45 minutes of wall-clock time.
