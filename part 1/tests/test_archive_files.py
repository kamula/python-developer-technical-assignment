from pathlib import Path

from archive_files import build_destination_path, discover_files, process_member


def test_build_destination_path_preserves_relative_structure(tmp_path):
    archive_root = tmp_path / "archive"
    home_dir = tmp_path / "home" / "alice"
    source_file = home_dir / "projects" / "api" / "auth.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("print('ok')", encoding="utf-8")

    destination = build_destination_path(archive_root, "alice", source_file, home_dir)

    assert destination == archive_root / "alice" / "projects" / "api" / "auth.py"


def test_discover_files_reads_home_and_archive(tmp_path):
    home_dir = tmp_path / "home" / "bob"
    archive_dir = tmp_path / "archive" / "bob"
    (home_dir / "notes").mkdir(parents=True)
    (archive_dir / "old").mkdir(parents=True)
    (home_dir / "notes" / "todo.txt").write_text("todo", encoding="utf-8")
    (archive_dir / "old" / "done.txt").write_text("done", encoding="utf-8")

    home_files, archive_files = discover_files(home_dir, archive_dir)

    assert [file.name for file in home_files] == ["todo.txt"]
    assert [file.name for file in archive_files] == ["done.txt"]


def test_process_member_marks_previous_archive_as_skipped(tmp_path):
    home_dir = tmp_path / "home" / "alice"
    archive_root = tmp_path / "archive"
    archived_file = archive_root / "alice" / "docs" / "api-design.md"
    archived_file.parent.mkdir(parents=True)
    home_dir.mkdir(parents=True)
    archived_file.write_text("already moved", encoding="utf-8")

    events = process_member("alice", home_dir, archive_root)

    assert len(events) == 1
    assert events[0].status == "skipped"
    assert "previous run" in events[0].reason


def test_process_member_moves_home_files(tmp_path):
    home_dir = tmp_path / "home" / "bob"
    archive_root = tmp_path / "archive"
    home_file = home_dir / "workspace" / "archive.py"
    home_file.parent.mkdir(parents=True)
    home_file.write_text("content", encoding="utf-8")

    events = process_member("bob", home_dir, archive_root)

    assert len(events) == 1
    assert events[0].status == "moved"
    assert not home_file.exists()
    assert (archive_root / "bob" / "workspace" / "archive.py").exists()
