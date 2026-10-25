# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-10-25

### Changed

- The PyInstaller build starts from `bloodhound/__main__.py`.

### Removed

- The top-level `main.py` launcher. Start the app with `bloodhound` (after
  `pip install .`) or `python -m bloodhound`.

## [1.0.0] - 2026-10-25

First packaged release. The single `main.py` script has become the `bloodhound` package.

### Added

- **Stop** button. Stopping discards only the files being copied at that moment;
  running again with the same destination resumes.
- The progress bar shows data processed and total in KB/MB/GB, the percentage and the current speed.
- **Elapsed** and **Remaining in this step** timers.
- Several source folders can be chosen at once (native multi-select dialog on
  Windows, a built-in dialog elsewhere).
- Hashing, copying and verifying run on a configurable pool of worker threads.
- Application icon (window, taskbar and executable).
- A list of files that couldn't be processed, shown at the end of a job.
- Installable package (`pip install .`) with a `bloodhound` command, `python -m bloodhound`,
  and a PyInstaller recipe for a standalone executable.
- Documentation (README, user guide, architecture notes), MIT license and a test suite.

### Changed

- Only files that share a size with another file are hashed when looking for
  duplicates; files with a unique size are hashed while they are copied instead.
- Copies are written to a temporary file and renamed into place when complete.
- Progress is measured in bytes rather than files, so large files move the bar smoothly.
- The window can be resized and adapts to high-DPI displays.

### Fixed

- Two source folders with the same name (e.g. `D:\Photos` and `E:\Photos`) could
  overwrite each other's files in the destination. They now go to `Photos` and `Photos (2)`.
- A whole drive added as a source copied its files straight into the destination
  root. It now gets its own `Drive X` folder.
- A destination inside a source folder was scanned as part of that source.
- One unreadable file could stop the whole job; it is now skipped and reported.
