"""Command line entry point.

    python -m ielts_agent "Is there an IELTS test in Almaty in December?"
    python -m ielts_agent --json "Алматыда желтоқсанда тест бар ма?"
"""
from __future__ import annotations

import argparse
import json
import sys

from .model_client import ModelError, complete
from .prompts import SYSTEM_PROMPT_V0


def ask(question: str, **kwargs):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_V0},
        {"role": "user", "content": question},
    ]
    return complete(messages, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ielts_agent", description="Ask the IELTS Candidate Assistant.")
    parser.add_argument("question", help="question in Kazakh, Russian or English")
    parser.add_argument("--json", action="store_true", help="print the reply and usage as JSON")
    args = parser.parse_args(argv)
    # The Windows console code page cannot print Kazakh letters; force UTF-8 output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not args.question.strip():
        print("Error: the question is empty.", file=sys.stderr)
        return 2
    try:
        reply = ask(args.question)
    except ModelError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({
            "answer": reply.text, "model": reply.model,
            "input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens,
            "seconds": round(reply.seconds, 2), "cost_usd": round(reply.cost_usd, 6),
        }, ensure_ascii=False, indent=2))
    else:
        print(reply.text)
        print(f"\n[{reply.model} | {reply.input_tokens} in / {reply.output_tokens} out tokens | "
              f"{reply.seconds:.2f}s | ${reply.cost_usd:.6f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
