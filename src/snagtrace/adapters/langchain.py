from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Optional
from uuid import UUID

try:
    from langchain_core.callbacks.base import BaseCallbackHandler
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "SnagTraceCallbackHandler requires langchain-core. "
        "Install it with: pip install snagtrace[langchain]"
    ) from exc

from ..core import Doctor, Span

logger = logging.getLogger("snagtrace")

# Hard cap on spans awaiting their on_tool_end/on_tool_error callback. This
# is exactly the failure this tool exists to catch (a runaway agent), so the
# adapter itself must not leak memory unboundedly while that happens. The
# oldest open span is evicted (and logged) rather than kept forever.
_MAX_OPEN_SPANS = 10_000


def _parse_args(input_str: str) -> Optional[dict]:
    try:
        parsed = json.loads(input_str)
        return parsed if isinstance(parsed, dict) else {"input": parsed}
    except (json.JSONDecodeError, TypeError):
        return None


class SnagTraceCallbackHandler(BaseCallbackHandler):
    """Feeds LangChain / LangGraph tool-call events into a snagtrace Doctor.

    Works with any LangChain agent executor and with LangGraph, since
    LangGraph runs on the same callback manager. Pass an instance in
    `config={"callbacks": [handler]}` (or `.with_config`) and call
    `handler.diagnose()` once the run finishes.

    Thread-safe: LangChain may invoke callbacks from multiple threads for
    parallel tool calls. Callback methods never raise. A malformed event
    is logged and dropped rather than breaking the host agent's execution,
    since a monitoring layer crashing the thing it's monitoring is worse
    than a missed span.
    """

    def __init__(self, doctor: Doctor, agent_id: str = "default"):
        self.doctor = doctor
        self.agent_id = agent_id
        self._step = 0
        self._open_spans: dict[UUID, Span] = {}
        self._lock = threading.Lock()

    def _next_step(self) -> int:
        with self._lock:
            self._step += 1
            return self._step

    def _track(self, run_id: UUID, span: Span) -> None:
        with self._lock:
            self._open_spans[run_id] = span
            if len(self._open_spans) > _MAX_OPEN_SPANS:
                oldest_run_id = next(iter(self._open_spans))
                dropped = self._open_spans.pop(oldest_run_id)
                logger.warning(
                    "snagtrace: dropping span for step %s (tool=%r), "
                    "more than %d tool calls are awaiting on_tool_end/"
                    "on_tool_error, which usually means callbacks aren't "
                    "firing correctly",
                    dropped.step_id,
                    dropped.tool,
                    _MAX_OPEN_SPANS,
                )

    def _pop(self, run_id: UUID) -> Optional[Span]:
        with self._lock:
            return self._open_spans.pop(run_id, None)

    def on_tool_start(
        self,
        serialized: Optional[dict[str, Any]],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        try:
            tool_name = (serialized or {}).get("name", "unknown_tool")
            span = Span(
                step_id=self._next_step(),
                agent_id=self.agent_id,
                kind="tool_call",
                tool=tool_name,
                args=_parse_args(input_str),
                status="ok",
                timestamp=time.time(),
            )
            self._track(run_id, span)
        except Exception:
            logger.exception("snagtrace: on_tool_start failed, dropping this span")

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            span = self._pop(run_id)
            if span is not None:
                self.doctor.feed(span)
        except Exception:
            logger.exception("snagtrace: on_tool_end failed, dropping this span")

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            span = self._pop(run_id)
            if span is not None:
                span.status = "error"
                span.error = str(error)
                self.doctor.feed(span)
        except Exception:
            logger.exception("snagtrace: on_tool_error failed, dropping this span")

    def diagnose(self):
        return self.doctor.diagnose()
