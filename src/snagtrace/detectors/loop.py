from __future__ import annotations

import json
from collections import deque

from ..core import Detector, Fault, Span


def _signature(span: Span) -> tuple:
    if not span.args:
        return (span.agent_id, span.tool, None)
    try:
        args_key = json.dumps(span.args, sort_keys=True, default=str)
    except (TypeError, ValueError):
        # args contains something json can't handle even with default=str
        # (e.g. a circular reference), so fall back to repr instead of
        # letting a single pathological span crash the whole detector.
        args_key = repr(span.args)
    return (span.agent_id, span.tool, args_key)


class LoopDetector(Detector):
    """Flags an agent repeating a semantically identical action without progress.

    Looks for the same (agent, tool, args) signature recurring `min_repeats`
    times within a sliding window of `window` spans. Purely structural, no
    LLM judge involved, so it never misses a loop because a judge got bored
    reading a long trace, and it never invents one either.
    """

    name = "loop"

    def __init__(self, window: int = 6, min_repeats: int = 3):
        if not isinstance(window, int) or isinstance(window, bool):
            raise TypeError(f"window must be an int, got {type(window).__name__}")
        if not isinstance(min_repeats, int) or isinstance(min_repeats, bool):
            raise TypeError(f"min_repeats must be an int, got {type(min_repeats).__name__}")
        if min_repeats < 2:
            raise ValueError("min_repeats must be >= 2")
        if window < 1:
            raise ValueError("window must be >= 1")
        if window < min_repeats:
            raise ValueError(
                f"window ({window}) must be >= min_repeats ({min_repeats}), "
                "otherwise a repeat can never reach min_repeats within the window"
            )
        self.window = window
        self.min_repeats = min_repeats

    def check(self, spans: list[Span]) -> list[Fault]:
        faults: list[Fault] = []
        recent: deque = deque(maxlen=self.window)
        flagged_signatures: set = set()

        for span in spans:
            sig = _signature(span)
            recent.append(sig)

            if sig in flagged_signatures:
                continue

            repeats = sum(1 for s in recent if s == sig)
            if repeats >= self.min_repeats:
                confidence = min(0.99, 0.6 + 0.1 * repeats)
                faults.append(
                    Fault(
                        step_id=span.step_id,
                        category="LOOP_FAILURE",
                        confidence=confidence,
                        evidence=(
                            f"agent={span.agent_id!r} repeated tool={span.tool!r} "
                            f"with identical arguments {repeats} times within the "
                            f"last {len(recent)} steps"
                        ),
                        detector=self.name,
                    )
                )
                flagged_signatures.add(sig)

        return faults
