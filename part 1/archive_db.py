#!/usr/bin/env python3
"""Database helpers for the file archiving assignment."""

from __future__ import annotations

import os
from contextlib import closing
from typing import Any

import psycopg2
import psycopg2.extras


def _candidate_hosts() -> list[str]:
    configured = os.getenv("ARCHIVE_DB_HOST") or os.getenv("DB_HOST") or "localhost"
    hosts = [configured]
    if configured != "postgres":
        hosts.append("postgres")
    return hosts


def connect_db():
    last_error = None
    for host in _candidate_hosts():
        try:
            return psycopg2.connect(
                host=host,
                port=int(os.getenv("ARCHIVE_DB_PORT", os.getenv("DB_PORT", "5432"))),
                dbname=os.getenv("ARCHIVE_DB_NAME", os.getenv("DB_NAME", "archivedb")),
                user=os.getenv("ARCHIVE_DB_USER", os.getenv("DB_USER", "archiveuser")),
                password=os.getenv(
                    "ARCHIVE_DB_PASSWORD",
                    os.getenv("DB_PASSWORD", "archivepass"),
                ),
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
        except psycopg2.Error as exc:  # pragma: no cover - exercised in integration
            last_error = exc
    raise last_error


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS archive_runs (
    id BIGSERIAL PRIMARY KEY,
    group_name TEXT NOT NULL,
    archive_root TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    duration_seconds NUMERIC(12, 3),
    total_moved INTEGER NOT NULL DEFAULT 0,
    total_skipped INTEGER NOT NULL DEFAULT 0,
    total_errors INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS archive_events (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES archive_runs(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    source_path TEXT NOT NULL,
    destination_path TEXT,
    status TEXT NOT NULL CHECK (status IN ('moved', 'skipped', 'error')),
    reason TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_archive_events_run_id
    ON archive_events(run_id);

CREATE INDEX IF NOT EXISTS idx_archive_events_run_status
    ON archive_events(run_id, status);
"""

MIGRATION_SQL = """
ALTER TABLE archive_runs
    ADD COLUMN IF NOT EXISTS archive_root TEXT;
ALTER TABLE archive_runs
    ALTER COLUMN archive_root SET DEFAULT '/tmp/file-archive';
UPDATE archive_runs
    SET archive_root = '/tmp/file-archive'
    WHERE archive_root IS NULL;
ALTER TABLE archive_runs
    ALTER COLUMN archive_root SET NOT NULL;

ALTER TABLE archive_runs
    ALTER COLUMN started_at SET DEFAULT NOW();

ALTER TABLE archive_runs
    ADD COLUMN IF NOT EXISTS duration_seconds NUMERIC(12, 3);
UPDATE archive_runs
    SET duration_seconds = EXTRACT(EPOCH FROM duration)
    WHERE duration_seconds IS NULL AND duration IS NOT NULL;

ALTER TABLE archive_runs
    ADD COLUMN IF NOT EXISTS error_message TEXT;

ALTER TABLE archive_events
    ADD COLUMN IF NOT EXISTS username TEXT;
UPDATE archive_events
    SET username = 'unknown'
    WHERE username IS NULL;
ALTER TABLE archive_events
    ALTER COLUMN username SET DEFAULT 'unknown';
ALTER TABLE archive_events
    ALTER COLUMN username SET NOT NULL;

ALTER TABLE archive_events
    ADD COLUMN IF NOT EXISTS event_time TIMESTAMPTZ;
UPDATE archive_events
    SET event_time = "timestamp"
    WHERE event_time IS NULL AND "timestamp" IS NOT NULL;
UPDATE archive_events
    SET event_time = NOW()
    WHERE event_time IS NULL;
ALTER TABLE archive_events
    ALTER COLUMN event_time SET DEFAULT NOW();
ALTER TABLE archive_events
    ALTER COLUMN event_time SET NOT NULL;

ALTER TABLE archive_events
    ALTER COLUMN "timestamp" SET DEFAULT NOW();
"""


def ensure_schema(conn) -> None:
    with conn, conn.cursor() as cursor:
        cursor.execute(SCHEMA_SQL)
        cursor.execute(MIGRATION_SQL)


def create_run(conn, group_name: str, archive_root: str) -> dict[str, Any]:
    with conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO archive_runs (group_name, archive_root)
            VALUES (%s, %s)
            RETURNING *
            """,
            (group_name, archive_root),
        )
        return dict(cursor.fetchone())


def log_event(
    conn,
    *,
    run_id: int,
    username: str,
    source_path: str,
    destination_path: str | None,
    status: str,
    reason: str,
) -> dict[str, Any]:
    with conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO archive_events
                (run_id, username, source_path, destination_path, status, reason, event_time, "timestamp")
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING *
            """,
            (run_id, username, source_path, destination_path, status, reason),
        )
        return dict(cursor.fetchone())


def finish_run(
    conn,
    *,
    run_id: int,
    total_moved: int,
    total_skipped: int,
    total_errors: int,
    status: str,
    error_message: str | None = None,
) -> dict[str, Any]:
    with conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE archive_runs
            SET
                finished_at = NOW(),
                duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at)),
                total_moved = %s,
                total_skipped = %s,
                total_errors = %s,
                status = %s,
                error_message = %s
            WHERE id = %s
            RETURNING *
            """,
            (total_moved, total_skipped, total_errors, status, error_message, run_id),
        )
        return dict(cursor.fetchone())


def fetch_runs(conn) -> list[dict[str, Any]]:
    with closing(conn.cursor()) as cursor:
        cursor.execute(
            """
            SELECT
                id,
                group_name,
                started_at,
                finished_at,
                duration_seconds,
                total_moved,
                total_skipped,
                total_errors,
                status,
                error_message
            FROM archive_runs
            ORDER BY started_at DESC, id DESC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def fetch_run(conn, run_id: int) -> dict[str, Any] | None:
    with closing(conn.cursor()) as cursor:
        cursor.execute(
            """
            SELECT
                id,
                group_name,
                archive_root,
                started_at,
                finished_at,
                duration_seconds,
                total_moved,
                total_skipped,
                total_errors,
                status,
                error_message
            FROM archive_runs
            WHERE id = %s
            """,
            (run_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def fetch_run_files(conn, run_id: int, status: str | None = None) -> list[dict[str, Any]]:
    with closing(conn.cursor()) as cursor:
        if status:
            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    source_path,
                    destination_path,
                    status,
                    reason,
                    COALESCE(event_time, "timestamp"::timestamptz) AS event_time
                FROM archive_events
                WHERE run_id = %s AND status = %s
                ORDER BY id
                """,
                (run_id, status),
            )
        else:
            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    source_path,
                    destination_path,
                    status,
                    reason,
                    COALESCE(event_time, "timestamp"::timestamptz) AS event_time
                FROM archive_events
                WHERE run_id = %s
                ORDER BY id
                """,
                (run_id,),
            )
        return [dict(row) for row in cursor.fetchall()]


def fetch_stats(conn) -> dict[str, Any]:
    with closing(conn.cursor()) as cursor:
        cursor.execute(
            """
            WITH busiest AS (
                SELECT group_name
                FROM archive_runs
                ORDER BY total_moved DESC, started_at DESC
                LIMIT 1
            ),
            recent AS (
                SELECT group_name
                FROM archive_runs
                ORDER BY started_at DESC, id DESC
                LIMIT 1
            )
            SELECT
                COUNT(*)::INT AS total_runs,
                COALESCE(SUM(total_moved), 0)::INT AS total_files_archived,
                COALESCE(SUM(total_skipped), 0)::INT AS total_skipped,
                COALESCE(SUM(total_errors), 0)::INT AS total_errors,
                (SELECT group_name FROM recent) AS most_recent_group,
                (SELECT group_name FROM busiest) AS busiest_group
            FROM archive_runs
            """
        )
        return dict(cursor.fetchone())
