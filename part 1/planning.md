# Part 1 Planning Notes

## 1A. Database schema

### `archive_runs`
- `id` bigint primary key
- `group_name` text
- `archive_root` text
- `started_at` timestamptz
- `finished_at` timestamptz
- `duration_seconds` numeric
- `total_moved` int
- `total_skipped` int
- `total_errors` int
- `status` text
- `error_message` text

Why this works:
- Each archiver invocation creates a new `archive_runs` row, so repeated archives of the same group are always distinguishable.
- The run row is inserted at the start, so if the process fails midway the partial run is still visible.
- `finished_at`, `duration_seconds`, totals, and `status` are updated at the end to show completion state and runtime.
- `archive_root` records which destination was used for that specific invocation.

### `archive_events`
- `id` bigint primary key
- `run_id` foreign key to `archive_runs`
- `username` text
- `source_path` text
- `destination_path` text nullable
- `status` text constrained to `moved | skipped | error`
- `reason` text
- `event_time` timestamptz

Why this works:
- Every file outcome is captured independently as it happens.
- `moved` rows show from where, to where, and when.
- `skipped` and `error` rows preserve the reason for examiner review.
- Because each event is committed immediately, partial progress remains visible if the run crashes.

### Migration decision

The schema is still created programmatically on first run, but the code also applies compatibility migrations for reused PostgreSQL volumes. This matters in practice because an examiner may restart containers without wiping the database volume. The application now safely adds missing columns such as `archive_root`, `error_message`, `duration_seconds`, `username`, and `event_time` when needed.

## 1B. API endpoint map

### `GET /runs`
- Returns all run summaries: `id`, `group_name`, `started_at`, `finished_at`, `duration_seconds`, `total_moved`, `total_skipped`, `total_errors`, `status`, `error_message`
- SQL concept: `SELECT ... FROM archive_runs ORDER BY started_at DESC, id DESC`

### `GET /runs/{id}`
- Returns one run plus every file event for that run
- SQL concept: `SELECT ... FROM archive_runs WHERE id = ?` then `SELECT ... FROM archive_events WHERE run_id = ? ORDER BY id`

### `GET /runs/{id}/files`
- Returns only file events for a run, optionally filtered by `status`
- SQL concept: `WHERE run_id = ? AND status = ?`
- Error handling: return HTTP 404 if the run does not exist

### `GET /stats`
- Returns cross-run aggregates: `total_runs`, `total_files_archived`, `total_skipped`, `total_errors`, `most_recent_group`, `busiest_group`
- SQL concept: `COUNT`, `SUM`, and small subqueries for most recent and busiest group

## 1C. Robustness cases

### Group does not exist
- Create the run row first, then mark it `failed` with a clear error message.
- Exit non-zero with no traceback.

### Group exists but has no members
- Finish the run successfully with zero totals.
- Print a clear informational message.

### Member home directory does not exist
- Log an `error` event for that user and continue with the remaining members.

### A file cannot be read due to permissions
- Log an `error` event for that file and continue processing other files.

### Same group archived a second time
- Create a fresh `archive_runs` row.
- Files already present in the archive are logged as `skipped`, which keeps the second run distinct from the first.

### Database connection fails during a run
- Because the run row and earlier file events are committed immediately, partial results remain visible.
- If the DB becomes unavailable, the script exits non-zero and marks the run failed if it still can.

## Additional implementation choices

### Hidden files
- The archiver ignores hidden files and hidden directories such as `.bashrc`, `.profile`, and `.bash_logout`.
- Reason: the assignment’s expected counts are based on the seeded business files in user home directories, not shell bootstrap files created by the OS.

### API hosting
- The FastAPI app is now started by Docker Compose as the `api` service.
- Reason: after a laptop restart, `docker compose up -d` should be enough to make `http://localhost:8000/` and `http://localhost:8000/docs` available without manually starting `uvicorn`.

### Verified happy-path result
- Clean developers run command:
  `docker compose exec testenv python3 archive_files.py --group developers --archive-root /tmp/archive-store-clean`
- Verified result:
  `Run 7 finished for group 'developers': moved=16 skipped=0 errors=0`
- This matches the assignment expectation for 8 Alice files and 8 Bob files.
