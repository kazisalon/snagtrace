class SnagTraceError(Exception):
    """Base class for all snagtrace errors."""


class InvalidSpanError(SnagTraceError):
    """A Span was constructed with invalid field values."""


class InvalidFaultError(SnagTraceError):
    """A Fault was constructed with invalid field values (e.g. bad confidence)."""


class TraceParseError(SnagTraceError):
    """A trace file (JSONL of Span records) could not be parsed."""

    def __init__(self, path: str, line_number: int, original: Exception):
        self.path = path
        self.line_number = line_number
        self.original = original
        super().__init__(f"{path}:{line_number}: {original}")


class DetectorError(SnagTraceError):
    """A detector raised while checking a trace.

    Wraps the original exception so `Doctor.diagnose` can report which
    detector misbehaved without losing the traceback.
    """

    def __init__(self, detector_name: str, original: Exception):
        self.detector_name = detector_name
        self.original = original
        super().__init__(f"detector {detector_name!r} raised {original!r}")
