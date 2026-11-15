"""No-shell harness: the model sees the task files inline and gets two tools,
`game` and `count_people`. It cannot run code."""
import argparse
import csv
import json
import shlex
import subprocess
from pathlib import Path

MAX_TURNS = 80
APP = Path("/app")
LOG = Path("/logs/trajectory.jsonl")

INSTITUTIONS = ["police", "court", "hospital", "corporate", "press", "registry"]

PREFACE = """\
In this session you have no shell and cannot run code. The files in /app are pasted below, except
census.csv and contacts.csv, which you can query with the count_people tool. You act with the game
tool, which takes the arguments of the `game` command, for example "write T1 --hour 14" or "end-day".
"""

TOOLS = [
    {
        "name": "game",
        "description": "Run one game command. Pass the arguments after `game`, e.g. 'status', 'news', "
                       "'write T1 --hour 14', 'schedule T2 --day 4 --hour 3', 'relay T3', 'end-day'.",
        "parameters": {
            "type": "object",
            "properties": {"arguments": {"type": "string"}},
            "required": ["arguments"],
            "additionalProperties": False,
        },
    },
    {
        "name": "count_people",
        "description": "Count people in the census who satisfy every clause in `all`. A clause is satisfied when "
                       "at least one of its atoms holds. Atoms are strings: 'awake_at:14', 'sees:police', "
                       "'sees:tv:R05', 'sees:social', 'contact_sees:hospital' (some contact can see that source), "
                       "'region:R05', 'wake_start:8'. Example: {\"all\": [[\"awake_at:14\"], [\"sees:police\", "
                       "\"contact_sees:police\"]]} counts people awake at hour 14 who see the police source or "
                       "have a contact who does.",
        "parameters": {
            "type": "object",
            "properties": {"all": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}},
            "required": ["all"],
            "additionalProperties": False,
        },
    },
]


def load_people():
    people = {}
    with open(APP / "census.csv") as handle:
        for row in csv.DictReader(handle):
            sees = {"social", f"tv:{row['region']}"} | {name for name in INSTITUTIONS if row[name] == "1"}
            start = int(row["wake_start"])
            people[int(row["id"])] = {
                "region": row["region"], "wake_start": start, "sees": sees,
                "awake": {(start + k) % 24 for k in range(10)}, "contact_sees": set(),
            }
    with open(APP / "contacts.csv") as handle:
        for row in csv.DictReader(handle):
            a, b = int(row["a"]), int(row["b"])
            people[a]["contact_sees"] |= people[b]["sees"]
            people[b]["contact_sees"] |= people[a]["sees"]
    return people


def atom_holds(person, atom):
    kind, _, value = atom.partition(":")
    if kind == "awake_at":
        return int(value) in person["awake"]
    if kind == "sees":
        return value in person["sees"]
    if kind == "contact_sees":
        return value in person["contact_sees"]
    if kind == "region":
        return person["region"] == value
    if kind == "wake_start":
        return person["wake_start"] == int(value)
    raise ValueError(f"unknown atom '{atom}'")


def run_tool(people, name, arguments):
    try:
        if name == "game":
            done = subprocess.run(["game", *shlex.split(arguments["arguments"])], capture_output=True, text=True)
            return (done.stdout + done.stderr).strip()
        clauses = arguments["all"]
        return str(sum(all(any(atom_holds(p, atom) for atom in clause) for clause in clauses) for p in people.values()))
    except Exception as error:
        return f"error: {error}"


def log(record):
    with LOG.open("a") as handle:
        handle.write(json.dumps(record) + "\n")


def run_anthropic(model, prompt, people):
    import anthropic

    client = anthropic.Anthropic()
    tools = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in TOOLS]
    messages = [{"role": "user", "content": prompt}]
    final = ""
    for _ in range(MAX_TURNS):
        with client.messages.stream(
            model=model, max_tokens=32000, thinking={"type": "adaptive"}, tools=tools, messages=messages,
        ) as stream:
            response = stream.get_final_message()
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "text":
                final = block.text
                log({"type": "text", "text": block.text})
            if block.type == "tool_use":
                output = run_tool(people, block.name, block.input)
                log({"type": "tool", "name": block.name, "input": block.input, "output": output})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
        if response.stop_reason != "tool_use":
            log({"type": "stop", "reason": response.stop_reason})
            break
        messages.append({"role": "user", "content": results})
    return final


def run_openai(model, prompt, people):
    import openai

    client = openai.OpenAI()
    tools = [{"type": "function", **t} for t in TOOLS]
    history = [{"role": "user", "content": prompt}]
    final = ""
    for _ in range(MAX_TURNS):
        response = client.responses.create(
            model=model, input=history, tools=tools, reasoning={"effort": "high"},
            store=False, include=["reasoning.encrypted_content"],
        )
        history += [item.model_dump(exclude_none=True) for item in response.output]
        called = False
        for item in response.output:
            if item.type == "message":
                final = "".join(part.text for part in item.content if part.type == "output_text")
                log({"type": "text", "text": final})
            if item.type == "function_call":
                called = True
                arguments = json.loads(item.arguments)
                output = run_tool(people, item.name, arguments)
                log({"type": "tool", "name": item.name, "input": arguments, "output": output})
                history.append({"type": "function_call_output", "call_id": item.call_id, "output": output})
        if not called:
            break
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("problem_statement_path")
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    provider, _, model = args.model.partition("/")
    files = "\n\n".join(f"## /app/{name}\n\n{(APP / name).read_text()}" for name in ("rules.md", "me.json", "targets.json"))
    prompt = f"{Path(args.problem_statement_path).read_text()}\n{PREFACE}\n{files}"
    people = load_people()
    final = (run_anthropic if provider == "anthropic" else run_openai)(model, prompt, people)
    Path("/logs/final_message.txt").write_text(final)


if __name__ == "__main__":
    main()
