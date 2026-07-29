from __future__ import annotations

import argparse
import json
import sys

from ..core import Doctor, Span
from ..detectors.budget import CostBudget
from ..detectors.loop import LoopDetector
from ..detectors.schema import ArgSchemaDetector
from ..exceptions import SnagTraceError, TraceParseError
from .html import render_html

# Exit codes: 0 = healthy, 1 = fault(s) found, 2 = could not run (bad input, bad args)
EXIT_HEALTHY = 0
EXIT_FAULTS_FOUND = 1
EXIT_ERROR = 2


def _load_spans(path: str) -> list[Span]:
    spans = []
    with open(path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TraceParseError(path, line_number, exc) from exc
            try:
                spans.append(Span.from_dict(raw))
            except SnagTraceError as exc:
                raise TraceParseError(path, line_number, exc) from exc
    return spans


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="snagtrace",
        description="Deterministic fault detection for AI agent execution traces.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="Diagnose a trace file (JSONL of spans)")
    report.add_argument("trace", help="Path to a JSONL file of snagtrace Span records")
    report.add_argument("--loop-window", type=int, default=6)
    report.add_argument("--loop-min-repeats", type=int, default=3)
    report.add_argument("--max-usd", type=float, default=None, help="Cost budget in USD")
    report.add_argument("--out", default=None, help="Write an HTML report to this path")
    report.add_argument(
        "--strict",
        action="store_true",
        help="Raise immediately if a detector errors, instead of skipping it",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "report":
        return EXIT_ERROR

    try:
        spans = _load_spans(args.trace)
    except FileNotFoundError:
        print(f"snagtrace: no such file: {args.trace}", file=sys.stderr)
        return EXIT_ERROR
    except TraceParseError as exc:
        print(f"snagtrace: failed to parse trace: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        detectors = [
            LoopDetector(window=args.loop_window, min_repeats=args.loop_min_repeats),
            ArgSchemaDetector(),
        ]
        if args.max_usd is not None:
            detectors.append(CostBudget(max_usd=args.max_usd))
    except ValueError as exc:
        print(f"snagtrace: invalid option: {exc}", file=sys.stderr)
        return EXIT_ERROR

    result = Doctor(detectors=detectors).diagnose(spans, strict=args.strict)

    if result.has_detector_errors:
        for error in result.errors:
            print(f"snagtrace: warning: {error}", file=sys.stderr)

    if result.is_healthy:
        print("snagtrace: no faults detected across", len(spans), "spans")
    else:
        first = result.first_fault
        print(f"snagtrace: {len(result.faults)} fault(s) found")
        print(
            f"  first fault -> step {first.step_id} [{first.category}] "
            f"(confidence {first.confidence:.2f}, via {first.detector})"
        )
        print(f"  {first.evidence}")

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(render_html(result))
        except OSError as exc:
            print(f"snagtrace: could not write report to {args.out}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(f"wrote report to {args.out}")

    return EXIT_HEALTHY if result.is_healthy else EXIT_FAULTS_FOUND


if __name__ == "__main__":
    sys.exit(main())
