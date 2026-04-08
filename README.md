# Python Developer Technical Assignment

This repository contains both required parts of the assignment:

- `part 1/` - File Archiving System using PostgreSQL, FastAPI, and a browser dashboard
- `part 2/` - LDAP group/member lookup script using Docker and OpenLDAP

## Prerequisites

Verified on this machine:

- `docker compose version` -> `Docker Compose version v5.1.0`
- `python3 --version` -> `Python 3.12.3`

If Docker Compose is not working on the machine, that should be flagged immediately because both parts depend on it.

## Part 1 Overview

Part 1 includes:

- `archive_files.py` - CLI archiver using `argparse`, `grp`, `pwd`, and PostgreSQL logging
- `archive_db.py` - schema creation and SQL access layer with compatibility migrations
- `main.py` - FastAPI application exposing the required endpoints
- `static/` - dashboard served at `http://localhost:8000/`
- `docker-compose.yml` - PostgreSQL, pgAdmin, test environment, and API service
- `debian-pkg/` - Debian package structure for `archive-files`
- `planning.md` - design answers for schema, API mapping, and robustness cases
- `test_plan.md` - manual verification checklist
- `tests/` - lightweight automated unit tests

Part 1 also includes dedicated planning and testing documents for the design and verification sections of the assignment:

- `part 1/planning.md`
- `part 1/test_plan.md`

### Part 1 verification guide

#### Step 1: start Docker and confirm services

```bash
cd "part 1"
docker compose up -d
docker compose ps
```

Expected:
- `postgres` healthy
- `pgadmin` running
- `api` running on port `8000`
- `testenv` running

Verified terminal output:

```text
part1-api-1        python:3.12-slim       ...   Up   0.0.0.0:8000->8000/tcp
part1-pgadmin-1    dpage/pgadmin4         ...   Up   0.0.0.0:5050->80/tcp
part1-postgres-1   postgres:15            ...   Up (healthy)   0.0.0.0:5432->5432/tcp
part1-testenv-1    debian:bookworm-slim   ...   Up
```

#### Step 2: run the archiver for the first time

Use a clean, configurable archive destination:

```bash
cd "part 1"
docker compose exec testenv python3 archive_files.py --group developers --archive-root /tmp/archive-store-clean
```

Verified output:

```text
Run 7 finished for group 'developers': moved=16 skipped=0 errors=0
```

Why 16:
- Alice has 8 seeded assignment files
- Bob has 8 seeded assignment files
- hidden shell dotfiles are intentionally ignored

#### Step 3: verify the database in pgAdmin

Open `http://localhost:5050` and sign in with:

- email: `admin@dewcis.com`
- password: `adminpass`

Register the PostgreSQL server in pgAdmin:

1. Right-click `Servers` -> `Register` -> `Server...`
2. In `General`, set `Name` to `Archive DB`
3. In `Connection`, use:
   - `Host name/address`: `postgres`
   - `Port`: `5432`
   - `Maintenance database`: `archivedb`
   - `Username`: `archiveuser`
   - `Password`: `archivepass`
4. Save

Then expand:

- `Servers`
- `Archive DB`
- `Databases`
- `archivedb`
- `Schemas`
- `public`
- `Tables`

Use this SQL query:

```sql
SELECT
  r.id,
  r.group_name,
  r.status,
  r.total_moved,
  r.total_skipped,
  r.total_errors,
  COUNT(e.id) AS event_rows
FROM archive_runs r
LEFT JOIN archive_events e ON e.run_id = r.id
GROUP BY r.id
ORDER BY r.id DESC;
```

Verified run summary for the clean developers run:

```text
 id | group_name | total_moved | total_skipped | total_errors |  status   |       archive_root
----+------------+-------------+---------------+--------------+-----------+--------------------------
  7 | developers |          16 |             0 |            0 | completed | /tmp/archive-store-clean
```

Verified event totals:

```text
 run_id | events | moved | skipped | errors
--------+--------+-------+---------+--------
      7 |     16 |    16 |       0 |      0
```

#### Step 4: verify the FastAPI service

No separate `uvicorn` command is required. The API now runs as a Docker Compose service on port `8000`.

Docs URL:

- `http://localhost:8000/docs`

Dashboard URL:

- `http://localhost:8000/`

Verified terminal check:

```bash
curl -I http://127.0.0.1:8000/docs
```

```text
HTTP/1.1 200 OK
server: uvicorn
content-type: text/html; charset=utf-8
```

Example API calls:

```bash
curl http://localhost:8000/runs
curl http://localhost:8000/stats
curl http://localhost:8000/runs/7
```

Example JSON shape:

```json
[
  {
    "id": 7,
    "group_name": "developers",
    "started_at": "2026-04-08T12:00:00+00:00",
    "finished_at": "2026-04-08T12:00:00+00:00",
    "duration_seconds": 0.125,
    "total_moved": 16,
    "total_skipped": 0,
    "total_errors": 0,
    "status": "completed",
    "error_message": null
  }
]
```

#### Step 5: open the dashboard

Open:

- `http://localhost:8000/`

Expected:
- summary cards with totals
- runs table with one row per run
- clicking a row shows every file event for that run
- auto-refresh occurs every 10 seconds

#### Step 6: run the archiver a second time

Run the same group again against the same archive destination:

```bash
cd "part 1"
docker compose exec testenv python3 archive_files.py --group developers --archive-root /tmp/archive-store-clean
```

Expected:
- a second, separate run record
- no crash
- files already present in the archive logged as `skipped`
- the dashboard shows the new run within 10 seconds

Run another group:

```bash
docker compose exec testenv python3 archive_files.py --group ops --archive-root /tmp/archive-store-clean
```

Expected:
- Carol and David files archived in a separate run
- `/stats` reflects both runs

#### Step 7: build and install the Debian package

Inside the container:

```bash
cd "part 1"
docker compose exec testenv dpkg-deb --build /workspace/debian-pkg /workspace/archive-files_1.0_all.deb
docker compose exec testenv dpkg -i /workspace/archive-files_1.0_all.deb
docker compose exec testenv archive-files --group hr --archive-root /tmp/archive-store-clean
```

Expected:
- package builds successfully
- `archive-files` resolves from `PATH`
- the installed command runs the archiver

### Part 1 testing

Automated unit tests:

```bash
cd "part 1"
../.venv/bin/pytest
```

Verified terminal output:

```text
============================= test session starts ==============================
collected 4 items
tests/test_archive_files.py ....                                         [100%]
============================== 4 passed in 0.14s ===============================
```

Manual verification scenarios are documented in:

- `part 1/test_plan.md`

### Part 1 design answers

Interview-ready planning answers are documented in:

- `part 1/planning.md`

Key decisions:
- `archive_runs` and `archive_events` are separate so every invocation is distinguishable and partial results remain queryable
- each file event is inserted and committed immediately
- a second archive of the same group becomes a new run with `skipped` rows for files already at destination
- missing groups fail cleanly with a non-zero exit and no traceback
- the schema bootstrap includes compatibility migrations so a reused database can still be upgraded programmatically

## Part 2 Overview

`part 2/ldap_query.py` performs the required two-step LDAP lookup:

1. search `ou=groups,dc=dewcis,dc=com` for the specific `posixGroup`
2. for each `memberUid`, search `ou=users,dc=dewcis,dc=com` for that user entry

Attributes requested:

- group search: `cn`, `gidNumber`, `memberUid`
- user search: `uid`, `cn`, `homeDirectory`

If the group does not exist, the script prints a clear error and exits non-zero without a traceback.

### Part 2 run guide

```bash
cd "part 2"
docker compose up -d
../.venv/bin/python ldap_query.py developers
```

Verified outputs:

```text
Group: developers (gidNumber: 2001)
Members:
alice | Alice Mwangi | /home/alice
bob | Bob Otieno | /home/bob
```

```text
Group: ops (gidNumber: 2002)
Members:
carol | Carol Njeri | /home/carol
david | David Kamau | /home/david
```

```text
Group: finance (gidNumber: 2003)
Members:
eve | Eve Wanjiku | /home/eve
frank | Frank Mutua | /home/frank
```

```text
Group: hr (gidNumber: 2004)
Members:
grace | Grace Achieng | /home/grace
```

Missing group case:

```bash
../.venv/bin/python ldap_query.py phantom
```

Verified output:

```text
Error: group 'phantom' not found in directory.
```

### Part 2 planning answers

- The script performs a two-step lookup: first the group entry, then each user entry referenced by `memberUid`.
- Group search base: `ou=groups,dc=dewcis,dc=com`
- User search base: `ou=users,dc=dewcis,dc=com`
- Group attributes: `cn`, `gidNumber`, `memberUid`
- User attributes: `uid`, `cn`, `homeDirectory`
- If the group does not exist, the script prints a clear error and exits with a non-zero status.

## Submission checklist

- source code for both parts
- `docker-compose.yml` files for both parts
- `ldap-seed.ldif` for Part 2
- Debian package structure in `part 1/debian-pkg/`
- tests and written verification guidance
- README with step-by-step execution instructions
