"""Run selectable eval cases, then judge the text they produced.

    python -m evals.run                 # run every case
    python -m evals.run profile day     # run only chosen cases
    python -m evals.run --list          # list cases
    python -m evals.run --no-judge      # skip the LLM grading

Cases live in cases.py; this file just runs them and does the judging. Each case
is isolated (its data is purged before the next), so they never interfere.
Photos come from evals/photos/ (gitignored); see that folder's README.
"""

import argparse
import asyncio
import json
import random
import re
import sys

from evals.cases import CASES, Day, photos
from evals.harness import build_world
from llm.openai_client import call_responses

_JUDGE_SYSTEM = (
    "You grade a food bot's text against one rule. Be strict; if unsure, fail. "
    'Return JSON only: {"pass": true/false, "why": "one line"}.'
)


async def _judge(world, text: str, rule: str) -> dict:
    raw = await call_responses(
        world.openai,
        model=world.settings.openai_model,
        system=_JUDGE_SYSTEM,
        user=f"RULE: {rule}\n\nTEXT:\n{text}",
        cache_key="eval-judge",
    )
    return json.loads(re.sub(r"^```\w*|```$", "", raw.strip()))


async def run(names: list[str], do_judge: bool) -> int:
    if not photos():
        print(
            "No photos in evals/photos/. Add real food photos (gitignored) and re-run."
        )
        return 0

    world = await build_world()
    to_judge: list[tuple[str, str, str]] = []
    try:
        for name in names:
            print(f"\n===== {name}: {CASES[name].__doc__.strip()} =====")
            day = Day(world, random.Random())
            try:
                await CASES[name](day)
            except Exception as error:  # one case failing must not abort the rest
                print(f"  ! case errored: {error}")
            to_judge += day.to_judge
            await world.purge()  # isolate each case from the next

        if do_judge and to_judge:
            print("\n===== JUDGEMENT =====")
            for label, text, rule in to_judge:
                try:
                    verdict = await _judge(world, text, rule)
                except Exception as error:  # a judge hiccup shouldn't sink the report
                    print(f"  SKIP {label} (judge failed: {error})")
                    continue
                print(f"  {'PASS' if verdict.get('pass') else 'FAIL'}  {label}")
                if not verdict.get("pass"):
                    print(f"        {verdict.get('why')}")
        return 0
    finally:
        await world.purge()
        await world.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run selectable food-bot eval cases.")
    parser.add_argument(
        "cases", nargs="*", help=f"cases to run (default all): {', '.join(CASES)}"
    )
    parser.add_argument("--no-judge", action="store_true", help="skip LLM grading")
    parser.add_argument("--list", action="store_true", help="list cases and exit")
    args = parser.parse_args()

    if args.list:
        for name, fn in CASES.items():
            print(f"  {name:<8} {fn.__doc__.strip()}")
        return
    names = args.cases or list(CASES)
    unknown = [n for n in names if n not in CASES]
    if unknown:
        sys.exit(f"unknown case(s): {', '.join(unknown)}. choices: {', '.join(CASES)}")
    sys.exit(asyncio.run(run(names, not args.no_judge)))


if __name__ == "__main__":
    main()
