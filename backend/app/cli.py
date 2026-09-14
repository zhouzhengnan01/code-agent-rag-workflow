import argparse
import asyncio
import json
import sys

from .agent import run_agent
from .db import init_db, resource_get


def main(argv=None):
    parser = argparse.ArgumentParser(prog="codezzn")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("exec", help="Run an agent non-interactively")
    run.add_argument("prompt", nargs="?", help="Prompt; use stdin when omitted or '-'")
    run.add_argument("--agent", dest="agent_id")
    run.add_argument("--json", action="store_true", dest="jsonl")
    args = parser.parse_args(argv)
    if args.command == "exec":
        init_db()
        prompt = args.prompt
        if not prompt or prompt == "-":
            prompt = sys.stdin.read()
        agents = [] if args.agent_id else None
        agent = resource_get("agents", args.agent_id) if args.agent_id else None
        if agent is None:
            from .db import resource_list
            agent = next((item for item in resource_list("agents") if item.get("enabled")), None)
        if not agent:
            parser.error("no enabled agent configured")
        result = asyncio.run(run_agent(agent, [], prompt.strip()))
        if args.jsonl:
            for event in result.get("events", []):
                print(json.dumps(event, ensure_ascii=False))
            print(json.dumps({"type": "turn_result", "content": result["content"], "usage": result["usage"], "runtime": result["runtime"], "sources": result["sources"]}, ensure_ascii=False))
        else:
            print(result["content"])
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
