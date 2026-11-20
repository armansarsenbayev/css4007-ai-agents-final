"""Command line entry point.

Ask the assistant (structured, validated answer):
    python -m ielts_agent "Is there an IELTS test in Almaty in December?"
    python -m ielts_agent --json "Алматыда желтоқсанда тест бар ма?"

Call a core function directly with JSON arguments (no model involved):
    python -m ielts_agent --call find_test_sessions '{"city": "Алматы", "module": "academic"}'
    python -m ielts_agent --call calculate_change_fee '{"session_id": "ALA-1212-CD", "action": "transfer"}'
"""
from __future__ import annotations

import argparse
import json
import sys

from .answer import validate_answer
from .core import FUNCTIONS
from .model_client import ModelError, complete
from .prompts import SYSTEM_PROMPT_V1


def ask(question: str, **kwargs):
    """One model request without tools. Returns (reply, validation)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_V1},
        {"role": "user", "content": question},
    ]
    reply = complete(messages, response_format={"type": "json_object"}, **kwargs)
    return reply, validate_answer(reply.text or "", tool_results=[], user_message=question)


def call_function(name: str, args_json: str) -> dict:
    if name not in FUNCTIONS:
        return {"error": f"Unknown function '{name}'.", "available": sorted(FUNCTIONS)}
    try:
        args = json.loads(args_json or "{}")
    except json.JSONDecodeError as e:
        return {"error": f"Arguments are not valid JSON: {e.msg}"}
    if not isinstance(args, dict):
        return {"error": "Arguments must be a JSON object."}
    if {"data", "today"} & set(args):  # test-only parameters, never set from outside
        return {"error": "Arguments 'data' and 'today' are not allowed."}
    try:
        return FUNCTIONS[name](**args)
    except TypeError as e:  # unknown or missing parameter
        return {"error": f"Wrong arguments for {name}: {e}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ielts_agent", description="Ask the IELTS Candidate Assistant.")
    parser.add_argument("text", help="a question in Kazakh, Russian or English, or JSON arguments with --call")
    parser.add_argument("--json", action="store_true", help="print the full structured answer and usage")
    parser.add_argument("--call", metavar="FUNCTION", help=f"run a core function: {', '.join(FUNCTIONS)}")
    args = parser.parse_args(argv)
    # The Windows console code page cannot print Kazakh letters; force UTF-8 output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.call:
        result = call_function(args.call, args.text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if "error" in result else 0

    if not args.text.strip():
        print("Error: the question is empty.", file=sys.stderr)
        return 2
    try:
        reply, check = ask(args.text)
    except ModelError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    usage = (f"[{reply.model} | {reply.input_tokens} in / {reply.output_tokens} out tokens | "
             f"{reply.seconds:.2f}s | ${reply.cost_usd:.6f} | validation: "
             f"{'ok' if check.ok else 'FAILED - ' + '; '.join(check.errors)}]")
    if args.json:
        print(json.dumps(check.answer, ensure_ascii=False, indent=2))
    else:
        print(check.answer["answer"])
    print("\n" + usage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
