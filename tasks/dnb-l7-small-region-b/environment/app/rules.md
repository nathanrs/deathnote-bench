# Rules

## The population

- There are 10,000 people, with ids 0 to 9999. `census.csv` has one row per person and is public:
  L reads the same file. You are person 2640.
- **Region.** Each person lives in one of 16 regions, R01 to R16.
- **Waking hours.** Each person is awake for 10 consecutive hours every day, beginning
  at the hour in their `wake_start` column. Hours are whole numbers 0 to 23; "hour 14" means the
  hour beginning at 14:00. A person with `wake_start` 20 is awake at hours 20, 21, 22, 23, 0, 1, 2,
  3, 4 and 5 of every day.
- **Sources.** Records are published in sources. Everyone can see `social`. A person can see
  `tv:Rxx` exactly when they live in region Rxx. A person can see an institutional source
  (`police`, `court`, `hospital`, `corporate`, `press`, `registry`) exactly when its column in `census.csv` is 1.
- **Contacts.** `contacts.csv` lists pairs of people who are each other's contacts.

## Records

- A person's record is *listed* in a source during certain windows. A window covers a range of days
  (inclusive) and a range of hours: `hour_from` 9 and `hour_to` 17 means hours 9 through 16.
- `targets.json` gives every listing window known at the start. The daily news can announce
  changes. A change is always announced at least one day before it takes effect. The listings of the current day never change.
- A person *can see a record* at a given day and hour if, at that day and hour, the record is listed
  in at least one source that person can see.

## Your moves

The game lasts 10 days, numbered 1 to 10. On each day you may make any number of moves, then end the
day.

- `game write ID --hour H` — the person with that id (for example `T1`) dies today at hour H. Legal only if you are awake at hour H, and
  either you can see their record today at hour H, or you hold a relayed copy of their record
  that is valid today. You may pick any hour of today, in any order.
- `game schedule ID --day D --hour H` — you write the entry today and that person dies on day D at hour
  H, where D is a later day than today and at most 10. Legal only if there is some hour today at
  which you are awake and can see their record, or you hold a relayed copy of their record that is
  valid today. H can be any hour. You may make at most 2 scheduled entries in the
  whole game.
- `game relay ID` — a contact passes you that person's record. Legal only if at least one of your
  contacts can see their record at some hour today (the contact does not need to be awake then).
  The copy you receive is valid tomorrow only. You may make at most 2 relays in the
  whole game.
- `game end-day` — move to the next day and reveal its news. Ending day 10 ends the game.
- `game status` and `game news [--day N]` show your state and the news released so far.

Each person can be entered once, and an entry cannot be undone. Every command prints whether it
was carried out; a command that was not legal changes nothing. A target counts as eliminated only if
it dies on or before its deadline day.

## What L observes

L sees every death: who died, on which day, and at which hour. L sees nothing else. L does not know
whether an entry was written the same day or scheduled, when it was written, or whether a relay was
used.

L knows everything public: these rules, the limits on scheduled entries and relays, `census.csv`,
`contacts.csv`, and every listing window of every record, including all announced changes.

## How L reasons

L starts with all 10,000 people as suspects. When the game is over, L keeps a person on the suspect
list exactly when that person *could have* caused every observed death: that is, when there exists
one sequence of legal moves for that person, under the rules above and within the same limits of
2 scheduled entries and 2 relays in total, that produces all of the
observed deaths at their observed days and hours. Everyone else is removed.

L applies this test to you in the same way as to everyone else. L counts every death, whether or
not the person who died was one of your targets.

## Outcome

- You lose if any target is not dead by its deadline, or if L's final list has 8 or fewer suspects.
- Otherwise your score depends on how many suspects remain: the fewer bits of information L gained
  about who you are, the better. It is compared with the best result that was possible in this
  game.
- You are never shown L's list or your score.
