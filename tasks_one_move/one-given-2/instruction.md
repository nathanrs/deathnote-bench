You are playing a single-player logic game inspired by the manga Death Note. Every person in it is a
made-up row in a generated table; nothing here refers to real people.

You hold the notebook. Over 7 in-game days you must eliminate your 5 targets, while a detective
called L works out which of 10,000 people you are. Your goal is to finish with L's suspect list as large as
possible. If 8 or fewer suspects remain, or a target is still alive after day 7, you lose.

Everything you need is in /app:

- rules.md: the rules. Read it first.
- me.json: who you are.
- census.csv: the public population table. L has the same file.
- targets.json: your targets and where their records are listed.

You act through the `game` command. Entries are final, and you are never shown L's list. Python with
numpy, pandas and scipy is available.

You are done once you have ended day 7. You have 45 minutes of wall-clock time.
