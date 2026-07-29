# Contributing

## Setup

```bash
pip install -e ".[dev,langchain]"
pytest
```

## Ground rules

- **Detectors must stay deterministic.** No LLM calls, no network access, no
  non-reproducible output. If a check needs an LLM judge, it belongs in a
  different, explicitly-labeled layer, not in `snagtrace.detectors`.
- **Every `Fault` needs real evidence.** `confidence` must reflect how
  certain the detector actually is, not be a placeholder constant.
- **New detectors validate their own config at `__init__`,** not partway
  through `check()`. Raise `TypeError`/`ValueError` with a message that says
  what was wrong and what was expected.
- **`Doctor.diagnose()` must keep working when a detector misbehaves.** If
  you add anything to the diagnosis path, make sure a raising detector still
  gets isolated (see `tests/test_robustness.py`).
- Add a regression test for every bug fix, ideally reproducing the original
  failure shape rather than a synthetic minimal case.

## Tests

`pytest -q` should be green with zero warnings before opening a PR. If you
touch the LangChain adapter, install the `langchain` extra and test against
real `langchain_core` callback events, not just hand-built `Span` objects.
See `tests/` for the pattern.
