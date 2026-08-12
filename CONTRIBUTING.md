# Contributing

1. Fork and create a focused branch.
2. Use Python 3.11 or newer and install `.[dev]` in a virtual environment.
3. Run `ruff check .` and `pytest` before opening a pull request.
4. Add deterministic tests for filter, provider, or report changes.
5. Never use live API calls in tests or commit credentials.

Changes that weaken a hard eligibility gate must be explicit and documented.
Do not pad a watchlist with securities that fail configured criteria.
