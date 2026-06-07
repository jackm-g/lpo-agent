"""Command-line entry point.

    python -m lpo.cli "question..." [--context ...] [--yes] [--no-confirm]
                      [--provider mock] [--max-retries N] [--json]

``--yes`` auto-approves the confirmation gate; ``--no-confirm`` disables the gate
entirely; otherwise the restatement is shown and approval is read from stdin.
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .models import SuccessResponse
from .orchestrator import Orchestrator


def _interactive_approval(restatement: str) -> bool:
    print("\n=== Proposed model (please review) ===")
    print(restatement)
    answer = input("\nApprove and solve? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LPO Agent — question to solved LP.")
    parser.add_argument("question")
    parser.add_argument("--context", default="")
    parser.add_argument("--provider", default=None, help="override LPO_PROVIDER (e.g. mock)")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--yes", action="store_true", help="auto-approve the gate")
    parser.add_argument("--no-confirm", action="store_true", help="disable the gate")
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args(argv)

    config = load_config()
    if args.provider:
        config.provider = args.provider

    orch = Orchestrator(config=config)
    approve_fn = (lambda _r: True) if args.yes else _interactive_approval

    resp = orch.run(
        question=args.question,
        context=args.context,
        require_human_confirmation=not args.no_confirm,
        max_retries=args.max_retries,
        approve_fn=approve_fn,
    )

    if args.json:
        print(resp.model_dump_json(indent=2))
        return 0

    if isinstance(resp, SuccessResponse):
        print("\n=== Decision ===")
        print(f"Objective: {resp.result.objective_value}")
        for k, v in resp.result.variables.items():
            print(f"  {k} = {v}")
        print("\n=== Explanation ===")
        print(resp.explanation)
        print(f"\ntrace_id: {resp.trace_id}")
        return 0

    print(f"\n[{resp.status}] {resp.message}")
    print(f"trace_id: {resp.trace_id}")
    return 0 if resp.status == "need_info" else 1


if __name__ == "__main__":
    sys.exit(main())
