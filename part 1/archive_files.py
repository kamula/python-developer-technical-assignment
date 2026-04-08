#!/usr/bin/env python3
"""Archive files for members of a Linux group and log events to PostgreSQL."""

from __future__ import annotations

import argparse
import grp
import os
import pwd
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from archive_db import create_run, ensure_schema, finish_run, log_event, connect_db


DEFAULT_ARCHIVE_ROOT = os.getenv("ARCHIVE_ROOT", "/tmp/file-archive")
VALID_STATUSES = {"moved", "skipped", "error"}


@dataclass
class FileEvent:
    username: str
    source_path: str
    destination_path: str
    status: str
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive files for Linux group members.")
    parser.add_argument("--group", required=True, help="Linux group to archive.")
    parser.add_argument(
        "--archive-root",
        default=DEFAULT_ARCHIVE_ROOT,
        help="Destination archive root. Can also be provided via ARCHIVE_ROOT.",
    )
    return parser.parse_args()


def build_destination_path(archive_root: Path, username: str, source_file: Path, home_dir: Path) -> Path:
    relative_path = source_file.relative_to(home_dir)
    return archive_root / username / relative_path


def discover_files(home_dir: Path, archive_user_root: Path) -> tuple[list[Path], list[Path]]:
    home_files: list[Path] = []
    archived_files: list[Path] = []

    def is_visible(path: Path, root: Path) -> bool:
        relative_parts = path.relative_to(root).parts
        return all(not part.startswith(".") for part in relative_parts)

    if home_dir.exists():
        home_files = sorted(
            path for path in home_dir.rglob("*") if path.is_file() and is_visible(path, home_dir)
        )
    if archive_user_root.exists():
        archived_files = sorted(
            path
            for path in archive_user_root.rglob("*")
            if path.is_file() and is_visible(path, archive_user_root)
        )

    return home_files, archived_files


def lookup_group_members(group_name: str) -> list[str]:
    group = grp.getgrnam(group_name)
    members = sorted(set(group.gr_mem))

    if not members:
        for entry in pwd.getpwall():
            if entry.pw_gid == group.gr_gid:
                members.append(entry.pw_name)

    return sorted(set(members))


def process_member(username: str, home_dir: Path, archive_root: Path) -> list[FileEvent]:
    events: list[FileEvent] = []
    archive_user_root = archive_root / username

    if not home_dir.exists():
        events.append(
            FileEvent(
                username=username,
                source_path=str(home_dir),
                destination_path=str(archive_user_root),
                status="error",
                reason="home directory does not exist",
            )
        )
        return events

    home_files, archived_files = discover_files(home_dir, archive_user_root)
    seen_archived_relative = {
        str(path.relative_to(archive_user_root)): path for path in archived_files
    }

    for source_file in home_files:
        destination = build_destination_path(archive_root, username, source_file, home_dir)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source_file.open("rb"):
                pass
            if destination.exists():
                events.append(
                    FileEvent(
                        username=username,
                        source_path=str(source_file),
                        destination_path=str(destination),
                        status="skipped",
                        reason="destination already exists",
                    )
                )
                continue
            shutil.move(str(source_file), str(destination))
            events.append(
                FileEvent(
                    username=username,
                    source_path=str(source_file),
                    destination_path=str(destination),
                    status="moved",
                    reason="file archived successfully",
                )
            )
        except PermissionError:
            events.append(
                FileEvent(
                    username=username,
                    source_path=str(source_file),
                    destination_path=str(destination),
                    status="error",
                    reason="permission denied",
                )
            )
        except OSError as exc:
            events.append(
                FileEvent(
                    username=username,
                    source_path=str(source_file),
                    destination_path=str(destination),
                    status="error",
                    reason=str(exc),
                )
            )

    home_relative_paths = {str(path.relative_to(home_dir)) for path in home_files}
    for relative_path, archived_path in seen_archived_relative.items():
        if relative_path in home_relative_paths:
            continue
        source_guess = home_dir / relative_path
        events.append(
            FileEvent(
                username=username,
                source_path=str(source_guess),
                destination_path=str(archived_path),
                status="skipped",
                reason="file already archived in a previous run",
            )
        )

    return events


def archive_group(group_name: str, archive_root: Path) -> int:
    conn = None
    run = None
    totals = {"moved": 0, "skipped": 0, "error": 0}

    try:
        conn = connect_db()
        ensure_schema(conn)
        run = create_run(conn, group_name=group_name, archive_root=str(archive_root))

        try:
            members = lookup_group_members(group_name)
        except KeyError:
            message = f"Error: group '{group_name}' not found."
            finish_run(
                conn,
                run_id=run["id"],
                total_moved=0,
                total_skipped=0,
                total_errors=1,
                status="failed",
                error_message=message,
            )
            print(message, file=sys.stderr)
            return 1

        if not members:
            finish_run(
                conn,
                run_id=run["id"],
                total_moved=0,
                total_skipped=0,
                total_errors=0,
                status="completed",
                error_message=None,
            )
            print(f"No members found for group '{group_name}'.")
            return 0

        for username in members:
            try:
                home_dir = Path(pwd.getpwnam(username).pw_dir)
            except KeyError:
                event = FileEvent(
                    username=username,
                    source_path=f"/home/{username}",
                    destination_path=str(archive_root / username),
                    status="error",
                    reason="user account not found",
                )
                log_event(
                    conn,
                    run_id=run["id"],
                    username=event.username,
                    source_path=event.source_path,
                    destination_path=event.destination_path,
                    status=event.status,
                    reason=event.reason,
                )
                totals[event.status] += 1
                continue

            for event in process_member(username, home_dir, archive_root):
                log_event(
                    conn,
                    run_id=run["id"],
                    username=event.username,
                    source_path=event.source_path,
                    destination_path=event.destination_path,
                    status=event.status,
                    reason=event.reason,
                )
                totals[event.status] += 1

        status = "completed" if totals["error"] == 0 else "completed_with_errors"
        finish_run(
            conn,
            run_id=run["id"],
            total_moved=totals["moved"],
            total_skipped=totals["skipped"],
            total_errors=totals["error"],
            status=status,
            error_message=None,
        )
        print(
            f"Run {run['id']} finished for group '{group_name}': "
            f"moved={totals['moved']} skipped={totals['skipped']} errors={totals['error']}"
        )
        return 0
    except Exception as exc:
        if conn is not None and run is not None:
            finish_run(
                conn,
                run_id=run["id"],
                total_moved=totals["moved"],
                total_skipped=totals["skipped"],
                total_errors=totals["error"] + 1,
                status="failed",
                error_message=f"database failure: {exc}",
            )
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()


def main() -> int:
    args = parse_args()
    return archive_group(args.group, Path(args.archive_root))


if __name__ == "__main__":
    raise SystemExit(main())
