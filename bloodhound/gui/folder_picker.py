"""Choosing several source folders at once.

On Windows the system folder dialog is used with multi-selection turned on
(Ctrl- or Shift-click several folders). Elsewhere, or if that dialog fails, a
small Tk dialog offers the same thing.
"""

from __future__ import annotations

import logging
import os
import string
import sys
import tkinter as tk
from tkinter import messagebox, ttk

log = logging.getLogger(__name__)


def ask_directories(parent: tk.Tk | tk.Toplevel, title: str, initialdir: str | None = None) -> list[str]:
    """Ask the user for one or more folders. Returns an empty list if they cancel."""
    if sys.platform == "win32":
        try:
            from bloodhound.gui import _win_folder_dialog

            owner = int(parent.wm_frame(), 16)
            paths = _win_folder_dialog.ask_directories(title, initialdir, owner)
            return [os.path.normpath(path) for path in paths]
        except OSError:
            log.warning("Native folder dialog failed; using the built-in one", exc_info=True)
    return FolderPickerDialog(parent, title, initialdir).show()


class FolderPickerDialog(tk.Toplevel):
    """A portable dialog listing the subfolders of one folder, several of which can be selected."""

    def __init__(self, parent: tk.Misc, title: str, initialdir: str | None = None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.minsize(420, 360)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._result: list[str] = []
        self._directory = ""  # "" is the list of drives on Windows
        self._location = tk.StringVar()

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        bar = ttk.Frame(frame)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.columnconfigure(0, weight=1)
        entry = ttk.Entry(bar, textvariable=self._location)
        entry.grid(row=0, column=0, sticky="ew")
        entry.bind("<Return>", lambda _event: self._navigate(self._location.get()))
        ttk.Button(bar, text="Go", width=5, command=lambda: self._navigate(self._location.get())).grid(
            row=0, column=1, padx=(6, 0)
        )
        ttk.Button(bar, text="Up", width=5, command=self._go_up).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(
            frame,
            text="Double-click to open a folder. Ctrl- or Shift-click to select several.",
            foreground="#555",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 4))

        self._listbox = tk.Listbox(frame, selectmode=tk.EXTENDED, activestyle="none", exportselection=False)
        self._listbox.grid(row=2, column=0, sticky="nsew")
        self._listbox.bind("<Double-Button-1>", self._open_selected)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self._listbox.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=scrollbar.set)

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Add selected", command=self._accept).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side="left", padx=(6, 0))
        self.bind("<Escape>", lambda _event: self._cancel())

        start = initialdir if initialdir and os.path.isdir(initialdir) else os.path.expanduser("~")
        self._navigate(start)

    def show(self) -> list[str]:
        self.grab_set()
        self._listbox.focus_set()
        self.wait_window()
        return self._result

    def _navigate(self, path: str) -> None:
        if path == "" and sys.platform == "win32":
            names = _drive_roots()
        else:
            path = os.path.abspath(os.path.expanduser(path))
            try:
                names = _subfolder_names(path)
            except OSError as exc:
                messagebox.showerror("Can't open folder", f"{path}\n\n{exc.strerror or exc}", parent=self)
                return
        self._directory = path
        self._location.set(path)
        self._listbox.delete(0, tk.END)
        self._listbox.insert(tk.END, *names)

    def _go_up(self) -> None:
        if not self._directory:
            return
        parent = os.path.dirname(self._directory)
        if parent == self._directory:  # at a drive root
            parent = "" if sys.platform == "win32" else parent
        self._navigate(parent)

    def _open_selected(self, _event: tk.Event | None = None) -> None:
        selection = self._listbox.curselection()
        if selection:
            self._navigate(os.path.join(self._directory, self._listbox.get(selection[0])))

    def _accept(self) -> None:
        selection = self._listbox.curselection()
        if selection:
            self._result = [os.path.join(self._directory, self._listbox.get(index)) for index in selection]
        elif self._directory:
            self._result = [self._directory]  # nothing selected: take the folder being shown
        self.destroy()

    def _cancel(self) -> None:
        self._result = []
        self.destroy()


def _drive_roots() -> list[str]:
    return [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.isdir(f"{letter}:\\")]


def _subfolder_names(path: str) -> list[str]:
    with os.scandir(path) as scan:
        return sorted((entry.name for entry in scan if entry.is_dir()), key=str.lower)
