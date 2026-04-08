# Part 1 Test Plan

## Automated coverage

Run:

```bash
cd "part 1"
../.venv/bin/pytest
```

Verified result:

```text
collected 4 items
tests/test_archive_files.py ....                                         [100%]
```

Covered by unit tests:
- destination path preserves directory structure
- discovery reads both live home files and previously archived files
- hidden dotfiles are ignored so only assignment files are archived
- second invocation behavior emits `skipped` for already archived files
- active home files are moved into the archive tree

## Manual verification checklist

### Happy path: developers
- Command: `docker compose exec testenv python3 archive_files.py --group developers --archive-root /tmp/archive-store-clean`
- Verified output: `Run 7 finished for group 'developers': moved=16 skipped=0 errors=0`
- Database check:
  `SELECT id, group_name, total_moved, total_skipped, total_errors, status FROM archive_runs WHERE id = 7;`
- Verified database result: `developers | 16 moved | 0 skipped | 0 errors | completed`
- Event check:
  `SELECT run_id, COUNT(*) AS events FROM archive_events WHERE run_id = 7 GROUP BY run_id;`
- Verified event result: `16` rows

### Happy path: second group
- Command: `docker compose exec testenv python3 archive_files.py --group ops --archive-root /tmp/archive-store-clean`
- Expected: separate run row, Carol and David files archived, `/stats` reflects both runs

### Second invocation: same group
- Command: `docker compose exec testenv python3 archive_files.py --group developers --archive-root /tmp/archive-store-clean`
- Expected: no crash, new run row exists, files already in archive logged as `skipped`

### Group not found
- Command: `docker compose exec testenv python3 archive_files.py --group phantom --archive-root /tmp/archive-store-clean`
- Expected: clear error message, non-zero exit, no traceback

### Empty group / no files
- Create a test group with no members, or rerun a group after every file is already archived into the chosen destination
- Expected: no crash and sensible zero or skipped totals

### Permission denied
- Remove read permission from a test file inside `testenv`, rerun the archive for that group
- Expected: one `error` event logged, run continues for other files

### API missing run
- Command: `curl http://localhost:8000/runs/99999`
- Expected: HTTP 404 with JSON body, not a 500

### Dashboard auto-refresh
- Keep `http://localhost:8000/` open, run the archiver, wait up to 10 seconds
- Expected: new row appears without a full page reload

### FastAPI docs
- Command: `curl -I http://127.0.0.1:8000/docs`
- Verified result: `HTTP/1.1 200 OK`

## Notes from verification

- The API is now started by Docker Compose, so `docker compose up -d` is enough to bring up `http://localhost:8000/` and `http://localhost:8000/docs`.
- The schema bootstrap now handles compatibility migrations for reused PostgreSQL volumes, so examiners do not need to create or patch tables manually.
