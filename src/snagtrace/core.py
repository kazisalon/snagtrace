from __future__ import annotations

import json
import logging
import threading
import time
import warnings
from dataclasses import asdict, dataclass, field, fields
from typing import Optional

from .exceptions import DetectorError, InvalidFaultError, InvalidSpanError

logger = logging.getLogger("snagtrace")

_VALID_KINDS = {"tool_call", "message", "other"}
_VALID_STATUSES = {"ok", "error"}


@dataclass
class Span:
    """One step in an agent execution trace.

    Mirrors the fields the OpenTelemetry GenAI semantic conventions capture,
    kept minimal so adapters for other frameworks stay small.
    """

    step_id: int
    agent_id: str = "default"
    kind: str = "tool_call"
    tool: Optional[str] = None
    args: Optional[dict] = None
    parent_step: Optional[int] = None
    tokens: Optional[int] = None
    max_tokens: Optional[int] = None
    cost_usd: float = 0.0
    status: str = "ok"
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not isinstance(self.step_id, int) or isinstance(self.step_id, bool):
            raise InvalidSpanError(f"step_id must be an int, got {self.step_id!r}")
        if self.kind not in _VALID_KINDS:
            raise InvalidSpanError(f"kind must be one of {_VALID_KINDS}, got {self.kind!r}")
        if self.status not in _VALID_STATUSES:
            raise InvalidSpanError(f"status must be one of {_VALID_STATUSES}, got {self.status!r}")
        if self.cost_usd < 0:
            raise InvalidSpanError(f"cost_usd cannot be negative, got {self.cost_usd!r}")
        if self.tokens is not None and self.tokens < 0:
            raise InvalidSpanError(f"tokens cannot be negative, got {self.tokens!r}")
        if self.args is not None and not isinstance(self.args, dict):
            raise InvalidSpanError(f"args must be a dict or None, got {type(self.args).__name__}")

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> Span:
        """Build a Span from a dict, ignoring unknown keys.

        Trace producers evolve independently of snagtrace's release cycle,
        so an unrecognized field (from a newer or third-party writer) is
        dropped with a warning rather than raising. A hard failure on a
        forward-compatible field would take down the whole diagnosis.
        """
        known = {f.name for f in fields(Span)}
        unknown = set(d) - known
        if unknown:
            warnings.warn(
                f"Span.from_dict: ignoring unknown field(s) {sorted(unknown)}",
                stacklevel=2,
            )
        return Span(**{k: v for k, v in d.items() if k in known})


@dataclass
class Fault:
    """A localized, deterministic finding produced by a detector."""

    step_id: int
    category: str
    confidence: float
    evidence: str
    detector: str

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise InvalidFaultError(f"confidence must be in [0, 1], got {self.confidence!r}")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DiagnosisResult:
    faults: list[Fault]
    errors: list[DetectorError] = field(default_factory=list)

    @property
    def first_fault(self) -> Optional[Fault]:
        if not self.faults:
            return None
        return min(self.faults, key=lambda f: f.step_id)

    @property
    def is_healthy(self) -> bool:
        return not self.faults

    @property
    def has_detector_errors(self) -> bool:
        return bool(self.errors)

    def to_dict(self) -> dict:
        return {
            "faults": [f.to_dict() for f in self.faults],
            "first_fault": self.first_fault.to_dict() if self.first_fault else None,
            "detector_errors": [str(e) for e in self.errors],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class Detector:
    """Base class for deterministic fault detectors.

    Subclasses implement `check`, which receives the full span history so
    far and returns any new faults found. Detectors must not call an LLM,
    since that keeps every result reproducible and free of confidence inflation.
    """

    name = "detector"

    def check(self, spans: list[Span]) -> list[Fault]:
        raise NotImplementedError


class Doctor:
    """Collects spans and runs deterministic detectors against them.

    Thread-safe: `feed` may be called concurrently from multiple agent
    threads (the common case for multi-agent systems), and `diagnose`
    snapshots the trace under the same lock so it never observes a
    partially-appended span list.
    """

    def __init__(self, detectors: Optional[list[Detector]] = None):
        self.detectors = detectors or []
        self.spans: list[Span] = []
        self._lock = threading.Lock()

    def feed(self, span: Span) -> None:
        if not isinstance(span, Span):
            raise InvalidSpanError(f"feed() expects a Span, got {type(span).__name__}")
        with self._lock:
            self.spans.append(span)

    def diagnose(
        self,
        spans: Optional[list[Span]] = None,
        strict: bool = False,
    ) -> DiagnosisResult:
        """Run every detector over the trace.

        By default (`strict=False`) a detector that raises is isolated: its
        error is recorded on the result and the remaining detectors still
        run, so one buggy or third-party detector can't take down an
        otherwise-healthy diagnosis in production. Pass `strict=True`
        (recommended in CI/tests) to raise immediately instead.
        """
        if spans is not None:
            trace = list(spans)
        else:
            with self._lock:
                trace = list(self.spans)

        faults: list[Fault] = []
        errors: list[DetectorError] = []
        for detector in self.detectors:
            detector_name = getattr(detector, "name", type(detector).__name__)
            try:
                faults.extend(detector.check(trace))
            except Exception as exc:  # noqa: BLE001 - intentional isolation boundary
                error = DetectorError(detector_name, exc)
                if strict:
                    raise error from exc
                logger.warning(str(error))
                errors.append(error)

        return DiagnosisResult(faults=faults, errors=errors)
