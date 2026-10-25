"""Smoke tests for the window. Skipped where no display is available."""

from __future__ import annotations

import tkinter as tk

import pytest

from bloodhound.core.models import FileError, JobResult, Phase, ProgressSnapshot


@pytest.fixture(scope="module")
def tk_root():
    # One Tk interpreter per process: creating a second one can fail to find tk.tcl in some virtualenvs.
    try:
        interpreter = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display: {exc}")
    interpreter.withdraw()
    yield interpreter
    interpreter.destroy()


@pytest.fixture
def root(tk_root):
    window = tk.Toplevel(tk_root)
    yield window
    window.destroy()


def test_window_renders_progress(root):
    from bloodhound.gui.main_window import MainWindow

    window = MainWindow(root)
    window.folder_list.add(["C:/one", "C:/two", "C:/one"])
    assert len(window.folder_list.paths) == 2

    window._render(ProgressSnapshot(
        phase=Phase.COPYING, files_done=10, files_total=40, bytes_done=1024**3, bytes_total=4 * 1024**3,
        elapsed=75, rate=80 * 1024**2, eta=38.4, current_file="C:/one/photo.jpg",
    ))
    root.update_idletasks()
    assert window.status_text.get() == "Step 3 of 4: Copying unique files"
    assert window.elapsed_text.get() == "Elapsed: 00:01:15"
    assert window.remaining_text.get() == "Remaining in this step: ~00:00:38"
    bar_text = window.progress_bar.itemcget(window.progress_bar._label, "text")
    assert bar_text == "1.00 GB of 4.00 GB  (25.0%)  ·  80.0 MB/s"


def test_portable_folder_picker_returns_selected_folders(root, tmp_path):
    from bloodhound.gui.folder_picker import FolderPickerDialog

    for name in ("Beta", "alpha", "Gamma"):
        (tmp_path / name).mkdir()
    (tmp_path / "file.txt").write_text("not a folder")

    dialog = FolderPickerDialog(root, "Pick", str(tmp_path))
    assert dialog._listbox.get(0, "end") == ("alpha", "Beta", "Gamma")
    dialog._listbox.selection_set(0)
    dialog._listbox.selection_set(2)
    dialog._accept()

    assert dialog._result == [str(tmp_path / "alpha"), str(tmp_path / "Gamma")]


def test_result_summary_mentions_problems():
    from bloodhound.gui.main_window import describe_result

    result = JobResult(sources=["a"], destination="b", files_found=3, unique_files=2, duplicate_files=1,
                       errors=[FileError("x", "Access is denied", Phase.COPYING)], elapsed=5)
    text = describe_result(result)
    assert "Duplicates skipped: 1" in text
    assert "Problems: 1" in text
    assert "Time: 00:00:05" in text
