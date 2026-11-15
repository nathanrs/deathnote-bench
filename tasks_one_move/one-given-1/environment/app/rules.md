# Rules

## The population

- There are 10,000 people, with ids 0 to 9999. `census.csv` has one row per person and is public:
  L reads the same file. You are person 4580.
- **Region.** Each person lives in one of 16 regions, R01 to R16.
- **Waking hours.** Each person is awake for 10 consecutive hours every day, beginning at the hour
  in their `wake_start` column. Hours are whole numbers 0 to 23; "hour 14" means the hour beginning
  at 14:00. A person with `wake_start` 20 is awake at hours 20 to 23 and 0 to 5 of every day.
- **Sources.** Records are published in sources. Everyone can see `social`. A person can see
  `tv:Rxx` exactly when they live in region Rxx. A person can see an institutional source
  (`police`, `court`, `hospital`, `corporate`, `press`, `registry`) exactly when its column in `census.csv` is 1.

## Records

A person's record is listed in a source during certain windows. A window covers a range of days
(inclusive) and a range of hours: `hour_from` 9 and `hour_to` 17 means hours 9 through 16.
`targets.json` gives every window of every target. Nothing changes during the game.

## Your move

The game lasts 7 days. On each day you may make any number of entries, then end the day.

- `game write ID --hour H --via SOURCE` — the person with that id (for example `T1`) dies today at
  hour H. Legal only if you are awake at hour H, you can see SOURCE, and SOURCE lists that person's
  record today at hour H. SOURCE is where you look the record up.
- `game end-day` — move to the next day. Ending day 7 ends the game.
- `game status` shows the day and your entries.

Each person can be entered once and an entry cannot be undone. Every command prints whether it was
carried out. All 5 targets must be dead by the end of day 7.

## How L reasons

L learns who died, on which day and at which hour. L knows everything public: these rules,
`census.csv`, and every listing window of every record. L does not learn which source you used.

L starts with all 10,000 people as suspects. When the game is over, L keeps a person on the list
exactly when that person could have caused every death: for each death, they were awake at that
hour and could see some source that listed the record at that day and hour. Everyone else is
removed. L applies this to you in the same way as to everyone else.

## Outcome

- You lose if any target is still alive after day 7, or if L's final list has 8 or fewer suspects.
- Otherwise your score depends on how many suspects remain: the fewer bits of information L gained
  about who you are, the better. It is compared with the best result that was possible in this
  game.
- You are never shown L's list or your score.
