"""The Bloodhound main window."""

from __future__ import annotations

import logging
import os
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from bloodhound import __app_name__, __version__
from bloodhound.core import MAX_WORKERS, DedupeJob, JobResult, Phase, ProgressSnapshot, default_workers
from bloodhound.gui.folder_picker import ask_directories
from bloodhound.gui.icon import load_image
from bloodhound.gui.widgets import ErrorListDialog, FolderList, TextProgressBar
from bloodhound.utils.formatting import format_bytes, format_duration, format_rate, shorten_path

log = logging.getLogger(__name__)

POLL_INTERVAL_MS = 150

PHASE_TITLES = {
    Phase.SCANNING: "Scanning folders",
    Phase.HASHING: "Comparing files",
    Phase.COPYING: "Copying unique files",
    Phase.VERIFYING: "Verifying copies",
}
PHASE_ORDER = tuple(PHASE_TITLES)

START_COLORS = {"background": "#4CAF50", "activebackground": "#43A047"}
STOP_COLORS = {"background": "#E53935", "activebackground": "#C62828"}
DISABLED_BACKGROUND = "#BDBDBD"
MUTED = "#5F5F5F"


class MainWindow(ttk.Frame):
    """Source list, destination, options, progress readout and Start/Stop buttons."""

    def __init__(self, root: tk.Tk | tk.Toplevel):
        super().__init__(root, padding=(16, 12, 16, 16))
        self.root = root
        self.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.destination = tk.StringVar()
        self.workers = tk.IntVar(value=default_workers())
        self.last_browsed_dir = os.path.expanduser("~")

        self._job: DedupeJob | None = None
        self._thread: threading.Thread | None = None
        self._job_error: BaseException | None = None
        self._quit_when_stopped = False

        base_font = tkfont.nametofont("TkDefaultFont")
        self._title_font = base_font.copy()
        self._title_font.configure(size=base_font.cget("size") + 6, weight="bold")
        self._bold_font = base_font.copy()
        self._bold_font.configure(weight="bold")

        self._build_header(row=0)
        self._build_sources(row=1)
        self._build_destination(row=2)
        self._build_options(row=3)
        self._build_progress(row=4)
        self._build_actions(row=5)

        self._set_running(False)
        self._show_ready()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.update_idletasks()
        root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())

    # -- layout ------------------------------------------------------------------

    def _build_header(self, row: int) -> None:
        header = ttk.Frame(self)
        header.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(1, weight=1)

        large = self.root.winfo_fpixels("1i") >= 120  # pick the sharper logo on high-DPI screens
        self._logo = load_image("bloodhound-64.png" if large else "bloodhound-48.png", master=self.root)
        if self._logo is not None:
            ttk.Label(header, image=self._logo).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ttk.Label(header, text=__app_name__, font=self._title_font).grid(row=0, column=1, sticky="sw")
        ttk.Label(header, text=f"v{__version__}", foreground=MUTED).grid(row=0, column=2, sticky="ne")
        ttk.Label(
            header,
            text="Finds the unique files across your folders and copies them, leaving duplicates behind.",
            foreground=MUTED,
        ).grid(row=1, column=1, columnspan=2, sticky="nw")

    def _build_sources(self, row: int) -> None:
        box = ttk.LabelFrame(self, text="Source folders", padding=10)
        box.grid(row=row, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        self.folder_list = FolderList(box, height=7, on_change=self._update_source_count)
        self.folder_list.grid(row=0, column=0, sticky="nsew")

        buttons = ttk.Frame(box)
        buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.add_button = ttk.Button(buttons, text="Add folders…", command=self._add_folders)
        self.add_button.pack(side="left")
        self.remove_button = ttk.Button(buttons, text="Remove selected", command=self.folder_list.remove_selected)
        self.remove_button.pack(side="left", padx=(6, 0))
        self.clear_button = ttk.Button(buttons, text="Clear", command=self.folder_list.clear)
        self.clear_button.pack(side="left", padx=(6, 0))
        self.source_count = ttk.Label(buttons, foreground=MUTED)
        self.source_count.pack(side="right")
        self._update_source_count()

    def _build_destination(self, row: int) -> None:
        box = ttk.LabelFrame(self, text="Destination folder", padding=10)
        box.grid(row=row, column=0, sticky="ew", pady=(10, 0))
        box.columnconfigure(0, weight=1)
        ttk.Entry(box, textvariable=self.destination, state="readonly").grid(row=0, column=0, sticky="ew")
        self.browse_button = ttk.Button(box, text="Browse…", command=self._choose_destination)
        self.browse_button.grid(row=0, column=1, padx=(6, 0))

    def _build_options(self, row: int) -> None:
        box = ttk.Frame(self)
        box.grid(row=row, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(box, text="Worker threads:").pack(side="left")
        self.workers_spinbox = ttk.Spinbox(box, from_=1, to=MAX_WORKERS, textvariable=self.workers, width=4)
        self.workers_spinbox.pack(side="left", padx=(6, 10))
        ttk.Label(box, text="More threads help SSDs and network drives; use 1–2 for spinning hard drives.",
                  foreground=MUTED).pack(side="left")

    def _build_progress(self, row: int) -> None:
        box = ttk.LabelFrame(self, text="Progress", padding=10)
        box.grid(row=row, column=0, sticky="ew", pady=(10, 0))
        box.columnconfigure(0, weight=1)

        self.status_text = tk.StringVar()
        self.detail_text = tk.StringVar()
        self.elapsed_text = tk.StringVar()
        self.remaining_text = tk.StringVar()

        # width=1 stops long text from widening the window; the grid stretches the labels instead.
        ttk.Label(box, textvariable=self.status_text, font=self._bold_font, width=1).grid(row=0, column=0, sticky="ew")
        ttk.Label(box, textvariable=self.detail_text, foreground=MUTED, width=1).grid(row=1, column=0, sticky="ew")
        self.progress_bar = TextProgressBar(box)
        self.progress_bar.grid(row=2, column=0, sticky="ew", pady=6)

        times = ttk.Frame(box)
        times.grid(row=3, column=0, sticky="ew")
        ttk.Label(times, textvariable=self.elapsed_text).pack(side="left")
        ttk.Label(times, textvariable=self.remaining_text).pack(side="right")

    def _build_actions(self, row: int) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=row, column=0, sticky="e", pady=(12, 0))
        button_style = {
            "foreground": "white",
            "disabledforeground": "#F5F5F5",
            "activeforeground": "white",
            "font": self._bold_font,
            "relief": "flat",
            "borderwidth": 0,
            "padx": 16,
            "pady": 6,
            "cursor": "hand2",
        }
        self.start_button = tk.Button(bar, text="Start scanning & copying", command=self._start, **button_style)
        self.start_button.pack(side="left")
        self.stop_button = tk.Button(bar, text="Stop", width=8, command=self._stop, **button_style)
        self.stop_button.pack(side="left", padx=(8, 0))

    # -- user actions ------------------------------------------------------------

    def _add_folders(self) -> None:
        paths = ask_directories(self.root, "Select folders to scan", self.last_browsed_dir)
        if paths:
            self.last_browsed_dir = os.path.dirname(os.path.normpath(paths[0])) or paths[0]
            self.folder_list.add(paths)

    def _choose_destination(self) -> None:
        folder = filedialog.askdirectory(
            parent=self.root, title="Select destination folder", initialdir=self.last_browsed_dir, mustexist=False
        )
        if folder:
            self.last_browsed_dir = os.path.dirname(os.path.normpath(folder)) or folder
            self.destination.set(os.path.normpath(folder))

    def _start(self) -> None:
        try:
            workers = int(self.workers.get())
        except (tk.TclError, ValueError):
            workers = default_workers()
        workers = max(1, min(MAX_WORKERS, workers))
        self.workers.set(workers)

        try:
            job = DedupeJob(self.folder_list.paths, self.destination.get(), workers=workers)
        except ValueError as exc:
            messagebox.showwarning("Can't start yet", str(exc), parent=self.root)
            return

        thread = threading.Thread(target=self._run_job, args=(job,), name="bloodhound-job", daemon=True)
        self._job, self._job_error, self._thread = job, None, thread
        self._set_running(True)
        thread.start()
        self.after(POLL_INTERVAL_MS, self._poll)

    def _stop(self) -> None:
        if self._job is not None and not self._job.cancel_requested:
            self._job.cancel()
            self.stop_button.configure(state="disabled", text="Stopping…", background=DISABLED_BACKGROUND)

    def _on_close(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            if not messagebox.askyesno(
                "Quit Bloodhound?",
                "A job is still running. Stop it and quit?\n\nFiles that were already copied are kept.",
                parent=self.root,
            ):
                return
            self._quit_when_stopped = True
            self._stop()
            return
        self.root.destroy()

    # -- running a job -----------------------------------------------------------

    def _run_job(self, job: DedupeJob) -> None:
        """Body of the background thread. The GUI only ever touches the job through snapshot()/cancel()."""
        try:
            job.run()
        except BaseException as exc:  # reported on the GUI thread by _finish
            log.exception("The job failed")
            self._job_error = exc

    def _poll(self) -> None:
        if self._job is None or self._thread is None:
            return
        self._render(self._job.snapshot())
        if self._thread.is_alive():
            self.after(POLL_INTERVAL_MS, self._poll)
        else:
            self._finish()

    def _render(self, snap: ProgressSnapshot) -> None:
        if snap.phase in PHASE_TITLES:
            step = PHASE_ORDER.index(snap.phase) + 1
            status = f"Step {step} of {len(PHASE_ORDER)}: {PHASE_TITLES[snap.phase]}"
            if self._job is not None and self._job.cancel_requested:
                status = "Stopping… letting the files in progress finish"
            self.status_text.set(status)

        current = f"  ·  {shorten_path(snap.current_file, 90)}" if snap.current_file else ""
        if snap.phase is Phase.SCANNING:
            self.detail_text.set(f"{snap.files_done:,} files found{current}")
            self.progress_bar.start_pulse()
            self.progress_bar.set_text(f"{format_bytes(snap.bytes_done)} found so far")
            self.remaining_text.set("Remaining: estimating…")
        else:
            self.detail_text.set(f"{snap.files_done:,} of {snap.files_total:,} files{current}")
            text = f"{format_bytes(snap.bytes_done)} of {format_bytes(snap.bytes_total)}  ({snap.fraction:.1%})"
            if snap.rate:
                text += f"  ·  {format_rate(snap.rate)}"
            self.progress_bar.set(snap.fraction, text)
            eta = "estimating…" if snap.eta is None else f"~{format_duration(snap.eta)}"
            self.remaining_text.set(f"Remaining in this step: {eta}")
        self.elapsed_text.set(f"Elapsed: {format_duration(snap.elapsed)}")

    def _finish(self) -> None:
        job, error = self._job, self._job_error
        self._job = self._thread = None
        if job is None:
            return
        self._set_running(False)
        if self._quit_when_stopped:
            self.root.destroy()
            return

        result = job.result
        if error is not None or result is None:
            reason = error if error is not None else "the job ended without a result"
            self.status_text.set("Something went wrong.")
            self.detail_text.set(f"{reason}")
            self.progress_bar.set(0.0, "")
            self.remaining_text.set("")
            messagebox.showerror("Bloodhound", f"The job stopped because of an unexpected error:\n\n{reason}",
                                 parent=self.root)
            return

        self.elapsed_text.set(f"Elapsed: {format_duration(result.elapsed)}")
        self.remaining_text.set("")
        if result.cancelled:
            self.status_text.set("Stopped.")
            self.detail_text.set(f"{result.files_copied:,} files copied before stopping. "
                                 "Start again with the same destination to resume.")
            self.progress_bar.set(job.snapshot().fraction, "Stopped")
            title = "Stopped"
        else:
            self.status_text.set("Done!")
            self.detail_text.set(f"{result.unique_files:,} unique files  ·  "
                                 f"{result.duplicate_files:,} duplicates skipped")
            self.progress_bar.set(1.0, f"{format_bytes(result.unique_bytes)} of unique files in the destination")
            title = "Finished"

        summary = describe_result(result)
        if result.errors:
            if messagebox.askyesno(title, f"{summary}\n\nShow the list of problems?", icon="warning",
                                   parent=self.root):
                ErrorListDialog(self.root, result.errors)
        else:
            messagebox.showinfo(title, summary, parent=self.root)

    # -- state -------------------------------------------------------------------

    def _set_running(self, running: bool) -> None:
        idle_state = "disabled" if running else "normal"
        for widget in (self.add_button, self.remove_button, self.clear_button, self.browse_button,
                       self.workers_spinbox):
            widget.configure(state=idle_state)
        self.folder_list.set_enabled(not running)
        self.start_button.configure(
            state=idle_state, background=DISABLED_BACKGROUND if running else START_COLORS["background"],
            activebackground=START_COLORS["activebackground"],
        )
        self.stop_button.configure(
            state="normal" if running else "disabled", text="Stop",
            background=STOP_COLORS["background"] if running else DISABLED_BACKGROUND,
            activebackground=STOP_COLORS["activebackground"],
        )

    def _show_ready(self) -> None:
        self.status_text.set("Ready.")
        self.detail_text.set("Add the folders to scan and choose where the unique files should go.")
        self.progress_bar.set(0.0, "")
        self.elapsed_text.set(f"Elapsed: {format_duration(0)}")
        self.remaining_text.set("")

    def _update_source_count(self) -> None:
        count = len(self.folder_list.paths)
        self.source_count.configure(
            text="No folders yet" if count == 0 else f"{count} folder{'s' if count != 1 else ''}"
        )


def describe_result(result: JobResult) -> str:
    """The summary shown when a job ends."""
    lines = []
    if result.cancelled:
        lines += ["The job was stopped before it finished. Files copied so far are kept; "
                  "start again with the same destination to resume.", ""]
    lines += [
        f"Files scanned: {result.files_found:,} ({format_bytes(result.bytes_found)})",
        f"Unique files: {result.unique_files:,} ({format_bytes(result.unique_bytes)})",
        f"Duplicates skipped: {result.duplicate_files:,} ({format_bytes(result.duplicate_bytes)})",
        f"Copied: {result.files_copied:,} ({format_bytes(result.bytes_copied)})",
    ]
    if result.files_already_present:
        lines.append(f"Already in the destination: {result.files_already_present:,}")
    if result.files_verified or not result.cancelled:
        verified = f"Verified: {result.files_verified:,}"
        if result.files_repaired:
            verified += f" ({result.files_repaired:,} had to be copied again)"
        lines.append(verified)
    if result.errors:
        lines.append(f"Problems: {len(result.errors):,} file(s) or folder(s) could not be processed")
    lines.append(f"Time: {format_duration(result.elapsed)}")
    return "\n".join(lines)
