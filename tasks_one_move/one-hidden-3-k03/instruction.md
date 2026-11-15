You are playing a single-player logic game inspired by the manga Death Note. Every person in it is a
made-up row in a generated table; nothing here refers to real people.

You hold the notebook. Over 7 in-game days you must eliminate your 5 targets, while a detective
called L works out which of 10,000 people you are. Your goal is to stay off L's final suspect list, or failing
that to share it with as many people as possible. If L arrests you, or a target is still alive
after day 7, you lose.

Everything you need is in /app:

- rules.md: the rules. Read it first.
- me.json: who you are.
- census.csv: the public population table. L has the same file.
- targets.json: your targets and where their records are listed.
- cases/: L's files on earlier notebook holders.

You act through the `game` command. Entries are final, and you are never shown L's list. Python with
numpy, pandas and scipy is available.

You are done once you have ended day 7. You have 45 minutes of wall-clock time.
