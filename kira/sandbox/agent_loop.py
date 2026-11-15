import argparse
import json
import subprocess


def game(*argv):
    return subprocess.run(["game", *argv], capture_output=True, text=True).stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("problem_statement_path")
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="low")
    args = parser.parse_args()
    rules = game("rules")
    while True:
        view = json.loads(game("view"))
        if view.pop("over"):
            break
        game("play", json.dumps(ask(args.model, rules, json.dumps(view), args.effort)))


if __name__ == "__main__":
    main()
