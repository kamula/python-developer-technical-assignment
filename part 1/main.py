#!/usr/bin/env python3
"""FastAPI service and dashboard for archive runs."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from archive_db import connect_db, ensure_schema, fetch_run, fetch_run_files, fetch_runs, fetch_stats


app = FastAPI(title="Archive Runs API", version="1.0.0")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: serialize(value) for key, value in row.items()}


def get_conn():
    conn = connect_db()
    ensure_schema(conn)
    return conn


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/runs")
def list_runs() -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        return [serialize_row(row) for row in fetch_runs(conn)]
    finally:
        conn.close()


@app.get("/runs/{run_id}")
def get_run(run_id: int) -> dict[str, Any]:
    conn = get_conn()
    try:
        run = fetch_run(conn, run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        files = fetch_run_files(conn, run_id)
        payload = serialize_row(run)
        payload["files"] = [serialize_row(item) for item in files]
        return payload
    finally:
        conn.close()


@app.get("/runs/{run_id}/files")
def get_run_files(
    run_id: int,
    status: str | None = Query(default=None, pattern="^(moved|skipped|error)$"),
) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        run = fetch_run(conn, run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        return [serialize_row(item) for item in fetch_run_files(conn, run_id, status=status)]
    finally:
        conn.close()


@app.get("/stats")
def stats() -> dict[str, Any]:
    conn = get_conn()
    try:
        return serialize_row(fetch_stats(conn))
    finally:
        conn.close()
