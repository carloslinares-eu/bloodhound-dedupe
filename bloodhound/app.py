"""Application entry point."""

from __future__ import annotations

import ctypes
import logging
import sys
import tkinter as tk

from bloodhound import __app_name__
from bloodhound.gui.icon import apply_window_icon
from bloodhound.gui.main_window import MainWindow

WINDOWS_APP_ID = "Bloodhound.UniqueFileCopier"


def _prepare_windows() -> None:
    """Sharp text on high-DPI screens, and our own taskbar icon instead of Python's."""
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(1)  # system DPI aware; Windows 8.1+
    except (AttributeError, OSError):
        try:
            ctypes.WinDLL("user32").SetProcessDPIAware()
        except (AttributeError, OSError):
            pass
    try:
        ctypes.WinDLL("shell32").SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except (AttributeError, OSError):
        pass


def create_root() -> tk.Tk:
    if sys.platform == "win32":
        _prepare_windows()
    root = tk.Tk(className=__app_name__)
    root.title(f"{__app_name__} - Unique File Scanner & Copier")
    apply_window_icon(root)
    return root


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = create_root()
    MainWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
