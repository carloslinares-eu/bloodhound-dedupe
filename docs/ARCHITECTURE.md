# Architecture

Bloodhound is split into a GUI-free **core** that does the work and a Tkinter
**gui** that drives it. The core can be used from scripts or tests without a
display.

```text
bloodhound/
├── app.py            main(): Windows DPI/taskbar setup, Tk root, icon, MainWindow
├── core/
│   ├── engine.py     DedupeJob: the 4 phases and the thread pool
│   ├── scanner.py    iter_files(), assign_root_labels()
│   ├── hashing.py    hash_file(), copy_file(): chunked, cancellable, report bytes
│   ├── progress.py   ProgressTracker: thread-safe counters, speed, ETA
│   ├── models.py     Phase, FileEntry, ProgressSnapshot, JobResult, FileError
│   └── errors.py     OperationCancelled, VerificationError
├── gui/
│   ├── main_window.py    layout, starting/stopping jobs, rendering progress
│   ├── widgets.py        FolderList, TextProgressBar, ErrorListDialog
│   ├── folder_picker.py  ask_directories(): native on Windows, Tk dialog elsewhere
│   ├── _win_folder_dialog.py  IFileOpenDialog via ctypes (multi-select folders)
│   └── icon.py           window icon and bundled images
└── utils/
    ├── formatting.py  sizes, speeds, durations, path shortening
    └── paths.py       case-aware path comparison
```

## Threads

```text
 GUI thread (Tk mainloop)          job thread                    worker pool (N threads)
 ───────────────────────          ──────────                     ───────────────────────
 Start ─► DedupeJob(...)
          Thread(job.run) ───────► scan folders
                                   hash phase ──── submit ─────► hash_file()  ─┐
 every 150 ms:                     copy phase ──── submit ─────► copy_file()  ─┼─► tracker.add_bytes()
   job.snapshot() ◄── lock ──────────────────────────────────────────────────────┘
   render labels/bar               verify phase ── submit ─────► hash_file()
 Stop ─► job.cancel() ── Event ──► every task checks the event between 1 MiB chunks
 thread finished? ─► job.result ─► summary dialog
```

- **The GUI thread** never touches files. It starts a `DedupeJob` on a
  background thread and polls `job.snapshot()` every 150 ms with `after()`.
  Tkinter isn't thread-safe, so nothing else calls into Tk.
- **The job thread** runs the phases in order and owns all bookkeeping
  (`JobResult`, the list of problems). Workers return values instead of
  mutating shared state, so the only lock is the progress tracker's.
- **The worker pool** (`concurrent.futures.ThreadPoolExecutor`) does the I/O and
  hashing. Threads give real parallelism here: file I/O and `hashlib` with large
  buffers both release the GIL. Only `workers × 4` tasks are queued at a time
  (`DedupeJob._parallel`), which keeps memory flat for millions of files and lets
  Stop take effect quickly.

## Cancellation

`DedupeJob.cancel()` sets a `threading.Event`. `hash_file` and `copy_file` check
it before every 1 MiB chunk and raise `OperationCancelled`; `_parallel` stops
queueing new work, drains the futures already running and then raises
`OperationCancelled` itself, which `run()` turns into `JobResult.cancelled = True`.

`copy_file` writes to `<dest>.bloodhound-partial` and only `os.replace`s it onto
`<dest>` when complete, deleting the partial file on any exception. A destination
file therefore either doesn't exist or is complete, which is what makes resuming
safe.

## Finding duplicates

1. Group all files by size. A group of one can't contain a duplicate.
2. Hash every file in the larger groups (in parallel).
3. Within each group, keep the first file (lowest discovery index) for each
   digest. Discovery order is deterministic (`iter_files` sorts each folder), so
   the result doesn't depend on thread timing.
4. Files that are kept but weren't hashed get their digest while being copied
   (`copy_file` hashes the stream), so the verify phase always has a source
   digest to compare against.

Destinations are `<destination>/<label>/<path relative to source>`. Labels are
unique per job (`assign_root_labels`), and any remaining clash, such as `a.txt`
and `A.txt` from a case-sensitive disk copied to a case-insensitive one, is
renamed `a (2).txt` by `_make_destinations_unique`.

## Progress, speed and time remaining

`ProgressTracker` keeps per-phase counters (`files_done/total`,
`bytes_done/total`) under one lock. Workers report bytes per chunk. Every 0.25 s
a sample `(time, bytes, files)` is recorded; samples older than the 5 s window
are dropped. The speed is the bytes processed since the oldest remaining sample
divided by the time since then, and the ETA is the bytes left divided by that
speed (or files left ÷ file rate when only empty files remain). Both are `None`
for the first half second of a phase, when there isn't enough data.

The `_progress_for` helper in the engine tops a file's progress up to its full
size if it ends early or fails, so the bar always reaches 100 %. When the verify
phase has to copy a file again it adds that extra work to the phase total.

## Native multi-select folder dialog (Windows)

Tk's `askdirectory` returns a single folder. `_win_folder_dialog.py` creates the
shell's `FileOpenDialog` COM object with `CoCreateInstance` and calls its vtable
directly through `ctypes` (no pywin32), setting
`FOS_PICKFOLDERS | FOS_ALLOWMULTISELECT | FOS_FORCEFILESYSTEM`. Results come back
as an `IShellItemArray` whose items are turned into paths with
`GetDisplayName(SIGDN_FILESYSPATH)`. Any failure raises `OSError`, and
`folder_picker.ask_directories` falls back to the portable Tk dialog.

## Tests

`tests/` uses pytest. The engine tests build real folder trees in a temporary
directory and run complete jobs, including cancellation, resume, repair after
corruption and name clashes. The progress tests use a fake clock. The GUI smoke
tests are skipped when no display is available.
