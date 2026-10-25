"""Reusable widgets: the folder list, a progress bar that shows text, and the problems dialog."""

from __future__ import annotations

import os
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Iterable
from tkinter import ttk

from bloodhound.core import FileError
from bloodhound.utils.paths import path_key


class FolderList(ttk.Frame):
    """A scrollable list of folders without duplicates. Ctrl/Shift-click selects several."""

    def __init__(self, master: tk.Misc, height: int = 7, on_change: Callable[[], None] | None = None):
        super().__init__(master)
        self._on_change = on_change
        self._paths: list[str] = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(
            self, selectmode=tk.EXTENDED, height=height, width=60, activestyle="none", exportselection=False
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.bind("<Delete>", lambda _event: self.remove_selected())
        self.listbox.bind("<Control-a>", self._select_all)

    @property
    def paths(self) -> list[str]:
        return list(self._paths)

    def add(self, paths: Iterable[str]) -> int:
        """Add folders that aren't listed yet; returns how many were added."""
        known = {path_key(path) for path in self._paths}
        added = 0
        for path in paths:
            path = os.path.normpath(path)
            if path_key(path) not in known:
                known.add(path_key(path))
                self._paths.append(path)
                self.listbox.insert(tk.END, path)
                added += 1
        if added:
            self._changed()
        return added

    def remove_selected(self) -> None:
        if str(self.listbox.cget("state")) == "disabled":
            return
        for index in reversed(self.listbox.curselection()):
            del self._paths[index]
            self.listbox.delete(index)
        self._changed()

    def clear(self) -> None:
        self._paths.clear()
        self.listbox.delete(0, tk.END)
        self._changed()

    def set_enabled(self, enabled: bool) -> None:
        self.listbox.configure(state="normal" if enabled else "disabled")

    def _select_all(self, _event: tk.Event) -> str:
        self.listbox.selection_set(0, tk.END)
        return "break"

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change()


class TextProgressBar(tk.Canvas):
    """A progress bar with a line of text drawn on top of it.

    ``set(fraction, text)`` shows determinate progress; ``start_pulse()`` shows
    a block sliding back and forth while the total amount of work is unknown.
    """

    TROUGH = "#E9E9E9"
    BORDER = "#BDBDBD"
    FILL = "#4CAF50"
    TEXT = "#1B1B1B"

    def __init__(self, master: tk.Misc, **kwargs):
        font = tkfont.nametofont("TkDefaultFont")
        height = font.metrics("linespace") + 12
        super().__init__(master, height=height, highlightthickness=0, borderwidth=0, background=self.TROUGH, **kwargs)
        self._fraction = 0.0
        self._pulse_position: float | None = None
        self._pulse_job: str | None = None

        self._border = self.create_rectangle(0, 0, 0, 0, outline=self.BORDER)
        self._bar = self.create_rectangle(0, 0, 0, 0, fill=self.FILL, width=0)
        self._label = self.create_text(0, 0, text="", fill=self.TEXT, font=font)
        self.bind("<Configure>", lambda _event: self._redraw())

    def set(self, fraction: float, text: str = "") -> None:
        self.stop_pulse()
        self._fraction = max(0.0, min(1.0, fraction))
        self.itemconfigure(self._label, text=text)
        self._redraw()

    def set_text(self, text: str) -> None:
        self.itemconfigure(self._label, text=text)

    def start_pulse(self) -> None:
        if self._pulse_job is None:
            self._pulse_position = 0.0
            self._tick()

    def stop_pulse(self) -> None:
        if self._pulse_job is not None:
            self.after_cancel(self._pulse_job)
            self._pulse_job = None
        self._pulse_position = None
        self._redraw()

    def _tick(self) -> None:
        self._pulse_position = (self._pulse_position + 0.015) % 2.0
        self._redraw()
        self._pulse_job = self.after(30, self._tick)

    def _redraw(self) -> None:
        width, height = self.winfo_width(), self.winfo_height()
        if self._pulse_position is not None:
            block = 0.25
            travel = self._pulse_position if self._pulse_position <= 1.0 else 2.0 - self._pulse_position
            left = travel * (1.0 - block) * width
            self.coords(self._bar, left, 0, left + block * width, height)
        else:
            self.coords(self._bar, 0, 0, self._fraction * width, height)
        self.coords(self._border, 0, 0, width - 1, height - 1)
        self.coords(self._label, width / 2, height / 2)


class ErrorListDialog(tk.Toplevel):
    """Lists every file that could not be processed, with a button to copy the list."""

    def __init__(self, parent: tk.Misc, errors: list[FileError]):
        super().__init__(parent)
        self.title(f"Problems ({len(errors):,})")
        self.transient(parent)
        self.minsize(520, 300)

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text="These files or folders could not be processed and were skipped:").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )

        self._text = "\n".join(f"[{error.phase.value}] {error.path} - {error.message}" for error in errors)
        text = tk.Text(frame, wrap="none", height=16, width=90)
        text.insert("1.0", self._text)
        text.configure(state="disabled")
        text.grid(row=1, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        yscroll.grid(row=1, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        xscroll.grid(row=2, column=0, sticky="ew")
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Copy to clipboard", command=self._copy).pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="left", padx=(6, 0))
        self.bind("<Escape>", lambda _event: self.destroy())

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._text)
