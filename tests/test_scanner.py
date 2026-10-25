from __future__ import annotations

import os

import pytest

from bloodhound.core.scanner import assign_root_labels, iter_files


def test_labels_use_folder_names():
    assert assign_root_labels([os.path.join("x", "Photos"), os.path.join("y", "Music")]) == ["Photos", "Music"]


def test_labels_for_repeated_names_are_numbered():
    sources = [os.path.join("a", "Photos"), os.path.join("b", "Photos"), os.path.join("c", "Photos")]
    assert assign_root_labels(sources) == ["Photos", "Photos (2)", "Photos (3)"]


@pytest.mark.skipif(os.name != "nt", reason="drive letters and case-insensitive names are Windows behavior")
def test_windows_labels_for_drive_roots_and_case():
    assert assign_root_labels(["D:\\", "E:\\"]) == ["Drive D", "Drive E"]
    assert assign_root_labels(["C:\\x\\photos", "C:\\y\\Photos"]) == ["photos", "Photos (2)"]


def test_iter_files_order_sizes_and_exclusion(make_tree):
    root = make_tree("src", {"b.txt": "bb", "a.txt": "a", "sub/z.txt": "zzz", "skip/x.txt": "x"})

    found = list(iter_files(str(root), exclude=[str(root / "skip")]))

    assert [(os.path.relpath(path, root), size) for path, size in found] == [
        ("a.txt", 1),
        ("b.txt", 2),
        (os.path.join("sub", "z.txt"), 3),
    ]


def test_iter_files_reports_unreadable_folders(tmp_path):
    errors = []
    found = list(iter_files(str(tmp_path / "missing"), on_error=lambda path, exc: errors.append(path)))
    assert found == []
    assert errors == [str(tmp_path / "missing")]
