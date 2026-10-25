"""Launches Bloodhound, so ``python main.py`` (and the IDE run button) keeps working.

The application itself lives in the ``bloodhound`` package; see README.md.
"""

from bloodhound.app import main

if __name__ == "__main__":
    raise SystemExit(main())
