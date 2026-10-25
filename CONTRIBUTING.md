# Contributing

Thanks for helping improve Bloodhound!

## Setting up

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

Then run the app with `bloodhound` (or `python -m bloodhound`) and the tests with `pytest`.

## Guidelines

- **Keep the core free of GUI code.** Anything under `bloodhound/core/` must
  work without Tkinter, so it can be tested and reused from scripts.
- **Only the GUI thread touches Tk.** Background code reports through
  `ProgressTracker` and `JobResult`; the window polls them.
- **No runtime dependencies.** Bloodhound runs on the standard library alone.
  Development tools belong in `requirements-dev.txt` and the `dev` extra in
  `pyproject.toml`.
- **Never risk the user's files.** Sources are read-only; destination writes go
  through `copy_file` (temporary file plus atomic rename).
- Add or update tests in `tests/` for behavior changes, and run `pytest` before
  sending a change.
- Follow the style of the surrounding code: type hints, short docstrings,
  4-space indentation, lines up to about 120 characters.
- Note user-visible changes in `CHANGELOG.md` under an "Unreleased" heading.

## Releasing

1. Bump `__version__` in `bloodhound/__init__.py` and move the changelog entries
   under the new version.
2. Build the executable with `pyinstaller packaging/bloodhound.spec` and try it.
3. Tag the release, e.g. `git tag v1.1.0`.
