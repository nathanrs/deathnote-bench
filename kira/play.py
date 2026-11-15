"""Play full games with a model in every seat: two Kiras against L and four detectives."""
import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from .engine import BLOCKS, CONNECTIONS, DISTRICTS, INVESTIGATORS, KIRAS, ROUTINES, Config, Game, busy_block, channels, traits

RULES = """\
# The game

A city has 100 residents, numbered 0 to 99. Every resident has a district ({districts}), a routine
({routines}) and a connection ({connections}). Each of the 100 combinations appears exactly once:
resident number = 20 x district index + 5 x routine index + connection index, in the orders listed.
So anyone who knows a resident's three traits knows their number, and the reverse.

Seven residents are players. Everyone else is a bystander.

- The Kira team: K1 and K2. Each has a notebook. They do not know who the other is.
- The investigators: L and detectives D1 to D4. All five have the police connection. They know each
  other's numbers.

## Days

The game lasts {days} days. Each day has four blocks: morning, afternoon, evening, night. A resident
is busy in one block, set by their routine (student: morning, office: afternoon, evening: evening,
night: night), and cannot act in it.

## News

Each morning 11 criminals are reported, each on one channel: 2 on `national`, 1 on each district's
`local:<district>`, and 1 on each of `wire:police`, `wire:press`, `wire:court`, `wire:hospital`.
A resident sees `national`, their own district's local channel, and the wire of their connection.
{national_delay} days after it is reported, every story is repeated nationally and everyone has seen it.

## The notebook

A Kira can write only criminals they have seen. Each Kira may write up to the day's limit
({caps} for days 1 to {days}). For each name they choose the block of death, which must be a block
when they are free. Every criminal who dies is 1 point for the Kira team.

Deaths are public: which criminal, the channel they were first reported on, and the block. Nobody is
told which Kira wrote the name.

## The bulletin

Each day K1, K2 and L may each post one public message. Posts are unsigned and appear the next
morning in random order. Everyone reads them. Anyone can claim to be anyone.

## What investigators can do

Each investigator takes one action a day, in a block when they are free:

- `tail`: pick up to {tail_size} residents. At the end of the day you learn whether anyone in the
  group wrote a name that day. A Kira who is being tailed is told so before writing.
- `bait`: place a fake criminal on a channel of your choice, reported tomorrow. It looks like any
  other criminal. If a Kira writes it, nobody dies, no point is scored, and all investigators learn
  which block it was written in. The team has {baits} baits in total.
- `arrest` (L only): name a resident. If they are a Kira, that Kira is out of the game. If not, the
  warrant is wasted. L has {warrants} warrants. Arrests are announced publicly.

Each investigator sees only the result of their own action. The investigators share a private
channel. Each of them posts one message a day there, in the order D1, D2, D3, D4, L.

## What the Kiras can do besides writing

- K1 sees, each morning, the investigators' full private channel and action log from the previous
  day: who did what, in which block, and the district each action was filed from (the acting
  investigator's home district).
- K2 has the eyes. Once per game K2 may write any resident by number. If that resident is L, the Kira
  team wins at once. If not, that resident dies and K2's home district is announced publicly.
- `approach`: each Kira may approach a resident twice per game. If that resident is the other Kira,
  the two are linked and can send each other one private message a day from then on. If the
  resident is an investigator, that investigator learns the approacher's resident number.

## Winning

- The Kira team wins if L is killed, or if at the end of day {days} they have judged at least
  {target} criminals and at least one Kira is still free.
- The investigators win otherwise: both Kiras arrested, or fewer than {target} criminals judged.
"""

KIRA_FORMAT = """\
Reply with one JSON object and nothing else:
{"notes_to_self": "what to remember tomorrow; you have no other memory",
 "writes": [{"criminal": "C1.3", "block": "evening"}],
 "approach": null or a resident number,
 "eyes": null or a resident number (K2 only),
 "bulletin_post": null or a public message for tomorrow's bulletin,
 "partner_message": null or a private message (only once linked)}"""

FORCE_FORMAT = """\
Reply with one JSON object and nothing else:
{"notes_to_self": "what to remember tomorrow; you have no other memory",
 "chat": "your message to the other investigators",
 "action": "tail" or "bait" or "arrest" or "none",
 "block": "morning" or "afternoon" or "evening" or "night",
 "targets": [resident numbers, for tail],
 "channel": "a channel, for bait",
 "resident": a resident number, for arrest,
 "bulletin_post": null or a public message for tomorrow's bulletin (L only)}"""


def rules_text(config):
    return RULES.format(
        districts=", ".join(DISTRICTS), routines=", ".join(ROUTINES), connections=", ".join(CONNECTIONS),
        days=config.days, caps=", ".join(str(c) for c in config.kill_caps[: config.days]),
        tail_size=config.tail_size, baits=config.baits, warrants=config.warrants,
        target=config.target_points, national_delay=config.days_until_national,
    )


def me(game, role):
    r = game.who[role]
    return {"role": role, "resident_number": r, **traits(r), "busy_block": busy_block(r), "channels_you_see": channels(r)}


def kira_view(game, role, tailed):
    day = game.day
    view = {
        "you": me(game, role), "day": day, "of_days": game.config.days,
        "names_you_may_write_today": game.config.kill_caps[min(day, len(game.config.kill_caps)) - 1],
        "team_points": game.points, "target_points": game.config.target_points,
        "you_are_being_tailed_today": tailed,
        "living_criminals_you_have_seen": game.visible_news(role),
        "criminals_you_wrote": game.kills_by[role],
        "this_mornings_bulletin": game.bulletin.get(day, []),
        "earlier_bulletins": {d: posts for d, posts in game.bulletin.items() if d < day},
        "public_record": game.public,
        "your_private_notes_from_the_game": game.private[role],
        "approaches_left": game.approaches_left[role], "linked_with_partner": game.linked,
        "partner_arrested": any(k in game.arrested for k in KIRAS if k != role),
    }
    if role == "K2":
        view["eyes_available"] = not game.eyes_used
    if role == "K1" and day > 1:
        log = game.force_log.get(day - 1, {})
        view["investigators_yesterday"] = {"actions": log.get("actions", []), "channel": log.get("chat", [])}
    return view


def force_view(game, role, todays_chat):
    day = game.day
    return {
        "you": me(game, role), "day": day, "of_days": game.config.days,
        "team": {inv: game.who[inv] for inv in INVESTIGATORS}, "dead_investigators": game.dead_investigators,
        "kira_points": game.points, "kira_target": game.config.target_points,
        "baits_left": game.baits_left, "warrants_left": game.warrants_left, "kiras_arrested": len(game.arrested),
        "this_mornings_bulletin": game.bulletin.get(day, []),
        "earlier_bulletins": {d: posts for d, posts in game.bulletin.items() if d < day},
        "public_record": game.public,
        "your_private_notes_from_the_game": game.private[role],
        "team_channel_and_actions_by_day": {d: {"actions": log["actions"], "channel": log["chat"]} for d, log in game.force_log.items()},
        "team_channel_today_so_far": todays_chat,
    }


def parse(text):
    match = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}


def ask(model, system, user, effort="low"):
    provider, _, name = model.partition("/")
    started = time.time()
    for attempt in range(3):
        try:
            if provider == "anthropic":
                import anthropic
                with anthropic.Anthropic().messages.stream(
                    model=name, max_tokens=32000, system=system, thinking={"type": "adaptive"},
                    output_config={"effort": effort}, messages=[{"role": "user", "content": user}],
                ) as stream:
                    reply = stream.get_final_message()
                text = "".join(block.text for block in reply.content if block.type == "text")
                reasoning = "\n".join(getattr(block, "thinking", "") or "" for block in reply.content if block.type == "thinking")
            else:
                import openai
                reply = openai.OpenAI().responses.create(
                    model=name, instructions=system, input=user, reasoning={"effort": effort, "summary": "auto"}, store=False,
                )
                text = reply.output_text
                reasoning = "\n".join(part.text for item in reply.output if item.type == "reasoning" for part in item.summary or [])
            result = parse(text)
            if result:
                return {**result, "_meta": {
                    "input_tokens": reply.usage.input_tokens, "output_tokens": reply.usage.output_tokens,
                    "seconds": round(time.time() - started, 1), "reasoning": reasoning,
                }}
        except Exception as error:
            if attempt == 2:
                return {"_error": str(error)[:200]}
            time.sleep(5 * (attempt + 1))
    return {}


def play(seed, config, kira_model, force_model, out_dir=None):
    game = Game.new(seed, config)
    rules = rules_text(config)
    memory = {role: "" for role in INVESTIGATORS + KIRAS}

    def turn(role, model, view, fmt):
        system = f"{rules}\nYou are playing {role}. This is a board game between AI players; every person in it is fictional.\n\n{fmt}"
        user = json.dumps({"your_notes_to_self_from_yesterday": memory[role], **view}, default=list)
        reply = ask(model, system, user)
        memory[role] = str(reply.get("notes_to_self", memory[role]))[:3000]
        return reply

    with ThreadPoolExecutor(max_workers=2) as pool:
        while game.winner is None:
            force, chat = {}, []
            for role in ["D1", "D2", "D3", "D4", "L"]:
                if game.active(role):
                    force[role] = turn(role, force_model, force_view(game, role, chat), FORCE_FORMAT)
                    if force[role].get("chat"):
                        chat.append({"from": role, "text": str(force[role]["chat"])[:600]})
            futures = {
                role: pool.submit(turn, role, kira_model, kira_view(game, role, game.tailed_now(role, force)), KIRA_FORMAT)
                for role in KIRAS if game.active(role)
            }
            kiras = {role: future.result() for role, future in futures.items()}
            posts = {role: (kiras.get(role) or {}).get("bulletin_post") for role in KIRAS}
            posts["L"] = (force.get("L") or {}).get("bulletin_post")
            game.resolve_day({k: str(v)[:400] for k, v in posts.items() if v}, force, kiras)
    result = {
        "seed": seed, "kira_model": kira_model, "force_model": force_model, "config": asdict(config),
        "winner": game.winner, "reason": game.reason, "points": game.points, "linked": game.linked,
        "arrested": game.arrested, "eyes_used": game.eyes_used, "dead_investigators": game.dead_investigators,
        "who": game.who, "kills_by": game.kills_by, "days_played": game.day,
    }
    if out_dir:
        path = Path(out_dir) / f"game_{seed}_{kira_model.split('/')[-1]}_vs_{force_model.split('/')[-1]}.json"
        path.write_text(json.dumps({**result, "history": game.history, "bulletin": game.bulletin, "public": game.public, "force_log": game.force_log, "private": game.private}, indent=1, default=list))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kira", default="anthropic/claude-sonnet-5-5")
    parser.add_argument("--force", default="anthropic/claude-sonnet-5-5")
    parser.add_argument("--games", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--days", type=int)
    parser.add_argument("--target", type=int)
    parser.add_argument("--tail-size", type=int)
    parser.add_argument("--caps")
    parser.add_argument("--out", default="results/kira")
    args = parser.parse_args()
    config = Config()
    if args.days:
        config.days = args.days
    if args.target:
        config.target_points = args.target
    if args.tail_size:
        config.tail_size = args.tail_size
    if args.caps:
        config.kill_caps = tuple(int(c) for c in args.caps.split(","))
    os.makedirs(args.out, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.games) as pool:
        results = list(pool.map(lambda s: play(s, config, args.kira, args.force, args.out), range(args.seed, args.seed + args.games)))
    for r in results:
        print(r["seed"], r["winner"], "|", r["reason"], "| points", r["points"], "| linked", r["linked"], "| arrested", r["arrested"], "| eyes", r["eyes_used"], "| days", r["days_played"])
    wins = sum(r["winner"] == "kira" for r in results)
    print(f"Kira team won {wins} of {len(results)}")
    with open(Path(args.out) / "games.jsonl", "a") as handle:
        for r in results:
            handle.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
