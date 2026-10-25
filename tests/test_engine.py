from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from bloodhound.core import DedupeJob, OperationCancelled, Phase
from bloodhound.core.hashing import PARTIAL_SUFFIX, copy_file, hash_file


def files_under(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()
    }


def test_copies_one_instance_of_each_unique_file(make_tree, tmp_path):
    first = make_tree("first", {"a.txt": "hello", "sub/b.txt": "world", "same-size-1.txt": "apple"})
    second = make_tree("second", {"copy-of-a.txt": "hello", "c.txt": "unique!", "same-size-2.txt": "lemon"})
    dest = tmp_path / "out"

    result = DedupeJob([first, second], dest, workers=4).run()

    assert files_under(dest) == {
        "first/a.txt": b"hello",
        "first/sub/b.txt": b"world",
        "first/same-size-1.txt": b"apple",
        "second/c.txt": b"unique!",
        "second/same-size-2.txt": b"lemon",
    }
    assert result.files_found == 6
    assert result.unique_files == 5
    assert result.duplicate_files == 1
    assert result.duplicate_bytes == 5
    assert result.files_copied == 5
    assert result.files_verified == 5
    assert result.files_repaired == 0
    assert not result.errors
    assert not result.cancelled


def test_first_folder_wins_regardless_of_thread_timing(make_tree, tmp_path):
    payload = os.urandom(64 * 1024)
    first = make_tree("first", {f"file{i:03}.bin": payload + bytes([i]) for i in range(60)})
    second = make_tree("second", {f"other{i:03}.bin": payload + bytes([i]) for i in range(60)})

    result = DedupeJob([first, second], tmp_path / "out", workers=8).run()

    assert result.unique_files == 60
    assert result.duplicate_files == 60
    assert sorted(os.listdir(tmp_path / "out")) == ["first"]


def test_empty_files_count_as_duplicates_of_each_other(make_tree, tmp_path):
    source = make_tree("src", {"empty1": b"", "empty2": b"", "data": b"x"})

    result = DedupeJob([source], tmp_path / "out").run()

    assert files_under(tmp_path / "out") == {"src/data": b"x", "src/empty1": b""}
    assert result.duplicate_files == 1


def test_sources_with_the_same_name_do_not_overwrite_each_other(make_tree, tmp_path):
    photos_d = make_tree("d/Photos", {"img.jpg": "from D"})
    photos_e = make_tree("e/Photos", {"img.jpg": "from E"})

    result = DedupeJob([photos_d, photos_e], tmp_path / "out").run()

    assert files_under(tmp_path / "out") == {"Photos/img.jpg": b"from D", "Photos (2)/img.jpg": b"from E"}
    assert result.files_repaired == 0


def test_destination_inside_a_source_is_not_scanned(make_tree):
    source = make_tree("src", {"a.txt": "a", "out/old.txt": "left over from before"})

    result = DedupeJob([source], source / "out").run()

    assert result.files_found == 1
    assert (source / "out" / "src" / "a.txt").read_text() == "a"


def test_second_run_resumes_instead_of_copying_again(make_tree, tmp_path):
    source = make_tree("src", {"a.txt": "aaa", "b.txt": "bbbb", "c.txt": "bbbb"})
    dest = tmp_path / "out"
    DedupeJob([source], dest).run()

    again = DedupeJob([source], dest).run()

    assert again.files_copied == 0
    assert again.files_already_present == 2
    assert again.files_verified == 2


def test_verification_repairs_a_corrupted_copy(make_tree, tmp_path):
    source = make_tree("src", {"a.txt": "original"})
    dest = tmp_path / "out"
    DedupeJob([source], dest).run()
    (dest / "src" / "a.txt").write_text("corrupt!")  # same size, different content

    result = DedupeJob([source], dest).run()

    assert result.files_repaired == 1
    assert (dest / "src" / "a.txt").read_text() == "original"


def test_cancel_before_start_copies_nothing(make_tree, tmp_path):
    source = make_tree("src", {"a.txt": "a"})
    job = DedupeJob([source], tmp_path / "out")
    job.cancel()

    result = job.run()

    assert result.cancelled
    assert not (tmp_path / "out").exists()
    assert job.snapshot().phase is Phase.FINISHED


def test_cancel_during_copy_keeps_finished_files_and_no_partials(make_tree, tmp_path):
    source = make_tree("src", {f"f{i:02}.bin": os.urandom(256 * 1024) for i in range(30)})
    dest = tmp_path / "out"
    job = DedupeJob([source], dest, workers=2)

    original_copy = job._copy_task
    calls = 0

    def copy_then_stop(entry):
        nonlocal calls
        calls += 1
        if calls == 5:
            job.cancel()
        return original_copy(entry)

    job._copy_task = copy_then_stop
    result = job.run()

    assert result.cancelled
    copied = files_under(dest)
    assert 0 < len(copied) < 30
    assert not any(name.endswith(PARTIAL_SUFFIX) for name in copied)
    for name, data in copied.items():
        assert (source / Path(name).name).read_bytes() == data


def test_progress_reaches_the_totals(make_tree, tmp_path):
    source = make_tree("src", {"a": b"1" * 3000, "b": b"2" * 3000, "c": b"3" * 10})
    job = DedupeJob([source], tmp_path / "out")
    job.run()

    snap = job.snapshot()
    assert snap.phase is Phase.FINISHED
    assert snap.bytes_done == snap.bytes_total == 6010  # the verify phase
    assert snap.files_done == snap.files_total == 3


@pytest.mark.parametrize(
    ("sources", "destination", "message"),
    [
        ([], "out", "at least one source"),
        (["src"], "", "destination"),
        (["missing"], "out", "doesn't exist"),
        (["src"], "src", "can't be one of the source"),
        (["src/inner"], "src", "can't be one of the source"),
    ],
)
def test_rejects_bad_folder_choices(tmp_path, monkeypatch, sources, destination, message):
    (tmp_path / "src" / "inner").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match=message):
        DedupeJob(sources, destination)


def test_copy_file_removes_partial_file_when_cancelled(tmp_path):
    source = tmp_path / "big.bin"
    source.write_bytes(os.urandom(64 * 1024))
    dest = tmp_path / "copy.bin"
    cancel = threading.Event()

    with pytest.raises(OperationCancelled):
        copy_file(str(source), str(dest), cancel, on_progress=lambda _n: cancel.set(), chunk_size=4096)

    assert list(tmp_path.iterdir()) == [source]


def test_copy_file_returns_the_hash_of_the_data(tmp_path):
    source = tmp_path / "a.bin"
    source.write_bytes(os.urandom(10_000))
    dest = tmp_path / "b.bin"

    digest = copy_file(str(source), str(dest), chunk_size=1024)

    assert dest.read_bytes() == source.read_bytes()
    assert digest == hash_file(str(source)) == hash_file(str(dest))
