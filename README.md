# Trade Store

[![CI](https://github.com/vishrutKulkarni2498/chronos-trade-store/actions/workflows/ci.yml/badge.svg)](https://github.com/vishrutKulkarni2498/chronos-trade-store/actions/workflows/ci.yml)

A REST API, built in Python, that receives trades, validates them against business rules, and stores them in a database. It was developed using **Test-Driven Development (TDD)** and ships with a **GitHub Actions** pipeline that runs regression tests and an **open-source vulnerability scan** which fails the build on critical vulnerabilities.

**At a glance**

- Enforces the trade rules: lower versions rejected, same versions replaced, past maturity dates rejected, matured trades marked as expired
- Keeps the full version history of every trade
- Single-trade and bulk submission endpoints, plus read endpoints with an expired filter
- Background expiry job with a **status endpoint** that shows the next run, the last run, and run totals (in UTC and IST)
- Business rules independent of HTTP, so other transports can reuse them
- Sample trades in `test_data/` for trying the API quickly
- Automated tests, coverage gate, vulnerability gate, and a Docker build in CI

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Business Rules](#2-business-rules)
3. [Assumptions and Design Decisions](#3-assumptions-and-design-decisions)
4. [Tech Stack](#4-tech-stack)
5. [Architecture](#5-architecture)
6. [Data Model](#6-data-model)
7. [API Reference](#7-api-reference)
8. [Getting Started](#8-getting-started)
9. [Sample Test Data](#9-sample-test-data)
10. [Running the Tests](#10-running-the-tests)
11. [Test-Driven Development Approach](#11-test-driven-development-approach)
12. [CI/CD Pipeline](#12-cicd-pipeline)
13. [Vulnerability Scanning](#13-vulnerability-scanning)
14. [Diagrams (PlantUML)](#14-diagrams-plantuml)
15. [Project Structure](#15-project-structure)
16. [Known Limitations](#16-known-limitations)
17. [Future Improvements](#17-future-improvements)

---

## 1. Problem Statement

Thousands of trades are sent to a single store, through any method of transmission. The goal is to build a trade store that organises and stores each trade in a defined sequence.

Sample data from the case study:

| Trade Id | Version | Counter-Party Id | Portfolio Id | Maturity Date | Created Date | Expired |
|----------|---------|------------------|--------------|---------------|--------------|---------|
| T1 | 1 | CP-1 | B1 | 20/05/2020 | `<today date>` | N |
| T2 | 2 | CP-2 | B1 | 20/05/2021 | `<today date>` | N |
| T2 | 1 | CP-1 | B1 | 20/05/2021 | 14/03/2015 | N |
| T3 | 3 | CP-3 | B2 | 20/05/2014 | `<today date>` | Y |

---

## 2. Business Rules

| # | Rule | Behaviour |
|---|------|-----------|
| R1 | A trade with a **lower version** than the one already stored for the same Trade Id | **Rejected** with an exception (`409 Conflict`) |
| R2 | A trade with the **same version** as an existing one | **Replaces** the existing record |
| R3 | A trade with a **maturity date earlier than today** | **Rejected** (`422 Unprocessable Entity`) |
| R4 | A stored trade whose **maturity date has passed** | Automatically marked **Expired = Y** |

A trade with a **higher version** than any stored version is accepted and stored as a new record (see Assumption A1).

---

## 3. Assumptions and Design Decisions

The brief leaves some points open. The interpretations below were chosen deliberately, and each one is covered by at least one automated test.

| ID | Topic | Assumption / Decision | Rationale |
|----|-------|-----------------------|-----------|
| **A1** | Version history | **All versions are retained.** A trade is uniquely identified by (`trade_id`, `version`). A higher version is inserted as a new row, and an older version is never overwritten. | The sample data shows `T2` v1 and `T2` v2 coexisting, which implies a composite key and a retained history. |
| **A2** | "Lower version" comparison | An incoming trade is compared with the **highest version currently stored** for that `trade_id`. If `incoming.version < max_stored_version`, it is rejected. | Guarantees versions can never move backwards, even if older versions are in the store. |
| **A3** | "Same version replaces" | If a row with the same (`trade_id`, `version`) exists, its fields are **overwritten** (upsert). This applies only when the version equals the stored one, and is subject to A2. | Directly implements rule R2. |
| **A4** | Maturity date equals today | A maturity date **equal to today is valid**. Only dates **strictly before** today are rejected. | The rule says "earlier than today's date". A trade maturing today has not yet matured. |
| **A5** | When a trade becomes expired | A trade is expired when `maturity_date < today`. A trade maturing today is **not** expired until tomorrow. | Consistent with A4. |
| **A6** | How expiry is applied | Two mechanisms work together. (1) A **scheduled job** persists `expired = true` for matured trades. (2) The `expired` flag is also **derived at read time** from the maturity date. | The job satisfies "automatically mark". Read-time derivation guarantees correct results between job runs. |
| **A7** | Sample row `T3` | `T3` has a past maturity date and `Expired = Y`. It would be rejected on ingestion under R3, so it is treated as **illustrative**, representing a trade that expired after being stored. | Rules R3 and the sample data can't both apply at insertion time. |
| **A8** | "Today" | "Today" means the **current date in UTC**. The clock is **injected** so tests can control it. | Removes timezone ambiguity and makes date tests deterministic. |
| **A9** | Created date | `created_date` (and `expired`) are **set by the server** at receipt time. If a client sends them, they are **ignored**. | The sample shows `<today date>` for new trades. Trusting a client-supplied audit date is unsafe. When a same-version trade replaces a record, `created_date` is preserved from the original. |
| **A10** | Date format | The API accepts and returns **ISO 8601** (`YYYY-MM-DD`). The `dd/MM/yyyy` format in the brief is a presentation format only. | ISO 8601 is unambiguous and a standard for APIs. |
| **A11** | Field validation | `trade_id`, `counter_party_id`, and `portfolio_id` are **required, non-empty strings**. `version` is a **positive integer** (≥ 1). `maturity_date` is a valid date. | Invalid input should fail fast with a clear error. |
| **A12** | "Version: 1.1" in the brief | Refers to the version of the **case study document**, not a trade attribute. | Not part of the trade schema. |
| **A13** | "Any method of transmission" | The business logic lives in a **service layer independent of transport**. REST is the entry point implemented here, and a bulk endpoint supports high-volume ingestion. Other transports (a queue consumer, file loader) could call the same service. | Keeps the rules in one place regardless of how trades arrive. |
| **A14** | Persistence | **SQL** (SQLAlchemy). **SQLite** is the default for local runs and tests. Any SQLAlchemy-supported database (for example PostgreSQL) can be used via configuration. | The composite key and version queries suit a relational model. |
| **A15** | Concurrency | Uniqueness of (`trade_id`, `version`) is enforced by a **database constraint**, and writes occur inside a **transaction**. | Prevents duplicate rows if two identical requests arrive at the same moment. See also [Known Limitations](#16-known-limitations). |
| **A16** | Authentication | **Not implemented.** The API is open. | Out of scope for this assignment. See [Future Improvements](#17-future-improvements). |
| **A17** | Order of validation | Input validation runs first, then the **maturity date check**, then the **version check**. If a trade breaks both R3 and R1, the maturity error (422) is reported. | The maturity check needs no database access, so it is cheap to do first. The order is fixed and covered by a test. |
| **A18** | Time zones in the scheduler status | Times are stored and computed in **UTC**. The `/scheduler/status` response also shows an **IST** (UTC+05:30) equivalent beside each time, as `*_ist` fields. IST is a **fixed offset** and is added only when building the response. | UTC stays the single source of truth, and IST is there for readability. India has no daylight saving, so a fixed offset is exact, and it avoids needing a system time zone database (Windows has none by default). |

---

## 4. Tech Stack

| Concern | Choice |
|---------|--------|
| Language | Python 3.11+ |
| Web framework | FastAPI (automatic validation and OpenAPI docs) |
| ORM / Database | SQLAlchemy with SQLite (swappable) |
| Scheduler | APScheduler (expiry job) |
| Testing | pytest, pytest-cov, freezegun, FastAPI `TestClient` |
| CI/CD | GitHub Actions |
| Vulnerability scan | Trivy (fails the build on `CRITICAL`) |
| Diagrams | PlantUML |
| Containerisation | Docker |

---

## 5. Architecture

The code is split into layers so business rules stay independent of HTTP and the database.

```
Client ──► API layer (FastAPI routers, request/response schemas)
              │
              ▼
          Service layer (business rules R1–R4, clock injected)
              │
              ▼
          Repository layer (database access via SQLAlchemy)
              │
              ▼
          Database (SQLite / PostgreSQL)

Scheduler ──► Service layer (expire matured trades)
    │
    └──► Monitor (records each run) ──► GET /scheduler/status
```

| Layer | Responsibility |
|-------|----------------|
| **API** | HTTP concerns, split into three routers (submit, read, scheduler): routing, status codes, mapping domain exceptions to HTTP errors |
| **Service** | All business validation: version rules, maturity rules, expiry |
| **Repository** | Persistence only, with no business logic |
| **Scheduler** | Periodically triggers the expiry operation in the service layer, and records the outcome of every run |

`app/main.py` only wires the application together (configuration, persistence, scheduler lifecycle, error handling, routers). The endpoints live in `app/routers/`, one module per section, and the same sections appear as groups in the Swagger UI.

### Exceptions

| Exception | Raised when | HTTP status |
|-----------|-------------|-------------|
| `LowerVersionError` | Incoming version is lower than the stored maximum | `409 Conflict` |
| `PastMaturityDateError` | Maturity date is earlier than today | `422 Unprocessable Entity` |
| `TradeNotFoundError` | Requested trade does not exist | `404 Not Found` |
| Validation error | Malformed or missing fields | `422 Unprocessable Entity` |

---

## 6. Data Model

**Table: `trades`**

| Column | Type | Notes |
|--------|------|-------|
| `trade_id` | string | Part of the composite primary key |
| `version` | integer | Part of the composite primary key |
| `counter_party_id` | string | Required |
| `portfolio_id` | string | Required |
| `maturity_date` | date | Required |
| `created_date` | date | Set by the server |
| `expired` | boolean | Persisted by the scheduler, also derived at read time |

- **Primary key:** (`trade_id`, `version`)
- **Index:** the composite primary key also indexes `trade_id` (it is the leading column), which keeps the "highest version" lookup fast
- **Index:** on `maturity_date` (efficient expiry sweep)

Scheduler run history is **not** stored in the database. It is kept in memory (see [`GET /scheduler/status`](#get-schedulerstatus-expiry-scheduler-status)).

---

## 7. API Reference

Endpoints are grouped into four sections, which also appear as groups in the Swagger UI: **Submit trades**, **Read trades**, **Scheduler** and **System**.

Interactive documentation is generated automatically when the app is running:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

| Section | Method and path | Purpose |
|---------|-----------------|---------|
| Submit trades | `POST /trades` | Submit one trade |
| Submit trades | `POST /trades/bulk` | Submit many trades |
| Read trades | `GET /trades` | List trades (optional `?expired=true\|false`) |
| Read trades | `GET /trades/{trade_id}` | All versions of one trade |
| Read trades | `GET /trades/{trade_id}/versions/{version}` | One specific version |
| Scheduler | `GET /scheduler/status` | Expiry scheduler status |
| System | `GET /health` | Health check |

### Section: Submit trades

#### `POST /trades`: submit a trade

**Request**
```json
{
  "trade_id": "T1",
  "version": 1,
  "counter_party_id": "CP-1",
  "portfolio_id": "B1",
  "maturity_date": "2030-05-20"
}
```

**Responses**

| Status | Meaning |
|--------|---------|
| `201 Created` | New trade (or new version) stored |
| `200 OK` | Same version already existed and was replaced |
| `409 Conflict` | Lower version than the stored one (R1) |
| `422 Unprocessable Entity` | Past maturity date (R3) or invalid input |

**Success body**
```json
{
  "trade_id": "T1",
  "version": 1,
  "counter_party_id": "CP-1",
  "portfolio_id": "B1",
  "maturity_date": "2030-05-20",
  "created_date": "2026-10-03",
  "expired": false
}
```

**Error body**
```json
{ "detail": "Trade T2 version 1 is lower than existing version 2." }
```

#### `POST /trades/bulk`: submit many trades

Accepts a JSON array of trades. Each trade is validated independently, and the response reports per-trade results (`created`, `replaced` or `rejected` with a reason), so one bad trade doesn't block the rest. The HTTP status is `200` as long as the request itself is a valid array.

**Response (example)**
```json
{
  "summary": { "total": 3, "created": 1, "replaced": 1, "rejected": 1 },
  "results": [
    { "index": 0, "trade_id": "T1", "version": 1, "status": "created", "detail": null },
    { "index": 1, "trade_id": "T1", "version": 1, "status": "replaced", "detail": null },
    {
      "index": 2,
      "trade_id": "T2",
      "version": 1,
      "status": "rejected",
      "detail": "Trade T2 version 1 is lower than existing version 2."
    }
  ]
}
```

Trades in a bulk request are processed in order, so a later trade is checked against the earlier ones in the same request.

### Section: Read trades

#### `GET /trades`: list trades

Returns all stored trades, ordered by `trade_id` then `version`. Optional filter: `?expired=true|false`. The filter uses the same read-time rule as the `expired` field, so it is correct even before the scheduled job has run.

#### `GET /trades/{trade_id}`: list all versions of a trade

Returns every stored version. `404` if the trade doesn't exist.

#### `GET /trades/{trade_id}/versions/{version}`: get one version

Returns a single (`trade_id`, `version`). `404` if not found.

### Section: Scheduler

#### `GET /scheduler/status`: expiry scheduler status

Reports whether the background expiry job is enabled and running, when it will next run, and how past runs went.

```json
{
  "enabled": true,
  "running": true,
  "interval_minutes": 60,
  "job_id": "expire-matured-trades",
  "current_time_utc": "2026-10-03T12:40:00Z",
  "current_time_ist": "2026-10-03T18:10:00+05:30",
  "next_run_time": "2026-10-03T13:00:00Z",
  "next_run_time_ist": "2026-10-03T18:30:00+05:30",
  "last_run": {
    "trigger": "schedule",
    "started_at": "2026-10-03T12:00:00.012Z",
    "started_at_ist": "2026-10-03T17:30:00.012+05:30",
    "finished_at": "2026-10-03T12:00:00.031Z",
    "finished_at_ist": "2026-10-03T17:30:00.031+05:30",
    "duration_ms": 19,
    "success": true,
    "trades_expired": 3,
    "error": null
  },
  "totals": { "runs": 5, "failures": 0, "trades_expired": 7 }
}
```

| Field | Meaning |
|-------|---------|
| `enabled` | Whether the scheduler was switched on (`ENABLE_SCHEDULER`) |
| `running` | Whether the scheduler is alive right now |
| `interval_minutes` | How often the job runs (`EXPIRY_JOB_INTERVAL_MINUTES`) |
| `current_time_utc` / `current_time_ist` | The server's current time, in UTC and in IST |
| `next_run_time` / `next_run_time_ist` | Next scheduled run in UTC and IST, or `null` when disabled or paused |
| `last_run.trigger` | `startup` (catch-up run when the app starts) or `schedule` |
| `last_run.started_at` / `finished_at` | When the latest run started and finished, each with an `_ist` equivalent |
| `last_run.duration_ms` | How long the latest run took |
| `last_run.success` / `error` | Outcome of the latest run, with the error text on failure |
| `last_run.trades_expired` | How many trades the latest run marked as expired |
| `totals` | Runs, failures, and trades expired since the process started |

Every time is in UTC (ending in `Z`), and the `*_ist` fields give the same instant in Indian Standard Time (`+05:30`). IST is for display only (assumption A18).

`last_run` is `null` until a run has happened, and the run history is kept **in memory**, so it resets when the application restarts and each instance reports only its own runs.

### Section: System

#### `GET /health`: health check

Returns `{"status": "ok"}`.

---

## 8. Getting Started

### Prerequisites

- Python 3.11 or newer
- Git
- (Optional) Docker

### Local setup

```bash
git clone https://github.com/vishrutKulkarni2498/chronos-trade-store.git
cd chronos-trade-store

python -m venv .venv
source .venv/bin/activate        # Windows (PowerShell): .venv\Scripts\Activate.ps1

pip install -r requirements-dev.txt   # runtime + test dependencies
```

### Run the API

```bash
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./trades.db` | SQLAlchemy connection string |
| `EXPIRY_JOB_INTERVAL_MINUTES` | `60` | How often the expiry job runs |
| `ENABLE_SCHEDULER` | `true` | Set to `false` to disable the background expiry job |

To watch the scheduler fire quickly, run with a one-minute interval:

```powershell
# Windows PowerShell
$env:EXPIRY_JOB_INTERVAL_MINUTES="1"
uvicorn app.main:app
```

```bash
# macOS / Linux
EXPIRY_JOB_INTERVAL_MINUTES=1 uvicorn app.main:app
```

Then call `GET /scheduler/status`. `last_run` shows a `startup` run straight away, and a `schedule` run appears about a minute later.

### Run with Docker

```bash
docker build -t trade-store .
docker run -p 8000:8000 trade-store
```

### Try it

```bash
curl -X POST http://localhost:8000/trades \
  -H "Content-Type: application/json" \
  -d '{"trade_id":"T1","version":1,"counter_party_id":"CP-1","portfolio_id":"B1","maturity_date":"2030-05-20"}'

curl http://localhost:8000/trades
curl http://localhost:8000/scheduler/status
```

On Windows PowerShell use `curl.exe` instead of `curl` (plain `curl` is an alias for a different command), and put the JSON in a file with `-d "@file.json"` to avoid quoting problems. Or use the Swagger UI at `/docs` and its "Try it out" buttons.

---

## 9. Sample Test Data

The [`test_data/`](test_data/) folder contains a JSON file of sample trades for trying the API without writing requests by hand.

**Send it to the bulk endpoint**

```bash
# macOS / Linux / Git Bash
curl -X POST http://localhost:8000/trades/bulk \
  -H "Content-Type: application/json" \
  -d @test_data/trades.json
```

```powershell
# Windows PowerShell
curl.exe -X POST http://localhost:8000/trades/bulk -H "Content-Type: application/json" -d "@test_data/trades.json"
```

You can also paste the file's content into `POST /trades/bulk` in the Swagger UI.

**Reading the result**

- The response lists one result per trade: `created`, `replaced`, or `rejected` with the reason.
- Trades that break a rule are reported as `rejected` and the rest are still stored, so you can see each business rule at work in a single request.
- Trades are processed in file order, so a lower version listed after a higher one for the same trade ID is rejected.
- Then call `GET /trades` to see what was stored, `GET /trades/{trade_id}` for the version history of one trade, and `GET /trades?expired=true` for expired trades.

Run the file against a fresh database for predictable results. To start clean, stop the app and delete `trades.db`.

---

## 10. Running the Tests

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=app --cov-report=term-missing

# Enforce the coverage threshold used in CI
pytest --cov=app --cov-fail-under=90
```

The tests use an isolated in-memory database and an **injected clock**, so they are deterministic and independent of the current date. `freezegun` is used to verify the real UTC clock, including the midnight rollover.

### Test files

| File | Covers |
|------|--------|
| `tests/test_schemas.py` | Input validation |
| `tests/test_clock.py` | UTC clock, midnight rollover, UTC to IST conversion |
| `tests/test_repository.py` | Database queries, duplicate keys, bulk expiry update |
| `tests/test_services.py` | Business rules R1 to R4 |
| `tests/test_scheduler.py` | Expiry job, scheduler wiring, run recording, status building |
| `tests/test_api.py` | Endpoints, status codes, bulk behaviour, application lifecycle |
| `tests/test_api_scheduler_status.py` | `GET /scheduler/status`, including IST fields and resilience |
| `tests/test_openapi_sections.py` | Endpoints grouped into named sections |

### Test coverage of the business rules

| Scenario | Rule / Assumption |
|----------|-------------------|
| Valid new trade is accepted | Baseline |
| Trade with lower version is rejected with `LowerVersionError` | R1, A2 |
| Trade with same version replaces existing record | R2, A3 |
| Replacement preserves original `created_date` | A9 |
| Trade with higher version is stored as a new row, and both versions are retained | A1 |
| Lower version is rejected even when several versions exist | A2 |
| Maturity date before today is rejected | R3 |
| Maturity date equal to today is accepted | A4 |
| Expiry job marks matured trades as expired | R4 |
| Expiry job leaves non-matured trades untouched | R4 |
| Trade maturing today is not expired, and is expired the next day | A5 |
| `expired` is correct at read time before the job runs | A6 |
| Maturity error takes precedence over version error | A17 |
| Client-supplied `created_date` / `expired` are ignored | A9 |
| UTC clock returns the UTC date and rolls over at midnight | A8 |
| Duplicate key at the repository raises and leaves the session usable | A15 |
| Missing or empty fields are rejected | A11 |
| Invalid version (0, negative) and invalid date are rejected | A11 |
| HTTP status codes map correctly (200, 201, 404, 409, 422) | API contract |
| Bulk endpoint reports per-trade success and failure | A13 |
| Scheduler registers the expiry job with the configured interval | R4 |
| Successful and failed job runs are recorded, and totals accumulate | Monitoring |
| Scheduler status reports enabled, running, next run and interval | Monitoring |
| A failed startup catch-up run does not stop the API | Monitoring |
| Status reports not running after shutdown | Monitoring |
| Scheduler status shows IST beside UTC times, and the same instant | A18 |
| UTC converts to IST (+05:30), including across midnight | A18 |
| Endpoints are grouped into named sections in the OpenAPI spec | API structure |

---

## 11. Test-Driven Development Approach

Development followed the **red, green, refactor** cycle:

1. **Red:** write a failing test describing the next behaviour
2. **Green:** write the minimum code to make it pass
3. **Refactor:** clean up while keeping all tests green

The git history reflects this rhythm. Commits are ordered so a failing test is committed before the implementation that satisfies it, for example:

```
test: reject trade with lower version (red)
feat: raise LowerVersionError for lower versions (green)
refactor: extract version lookup into repository
```

Build order: schema and service rule tests first, then the repository, then API endpoints, then the scheduler and its status endpoint, then the pipeline.

---

## 12. CI/CD Pipeline

The pipeline is defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) and runs on every **push** and **pull request**.

| Stage | Purpose | Fails the build when |
|-------|---------|----------------------|
| **1. Checkout and set up Python** | Prepare the environment (Python 3.11 and 3.12 matrix) | Setup fails |
| **2. Install dependencies** | Pinned install from `requirements-dev.txt` | Install fails |
| **3. Regression tests** | Run the full pytest suite with coverage | Any test fails, or coverage is below 90% |
| **4. Vulnerability scan** | Scan dependencies for known OSS vulnerabilities | Any **CRITICAL** vulnerability is found |
| **5. Docker build** | Verify the image builds | Build fails |

Because the whole suite runs on every change, it acts as an automated **regression test** gate.

---

## 13. Vulnerability Scanning

**Tool:** [Trivy](https://github.com/aquasecurity/trivy), run through `aquasecurity/trivy-action`.

**Policy:** the build **fails** when a vulnerability of `CRITICAL` severity is detected in the project's dependencies.

Relevant configuration:

```yaml
- name: Trivy scan (CRITICAL, fails the build)
  uses: aquasecurity/trivy-action@0.28.0   # pinned, not @master
  with:
    scan-type: fs
    scan-ref: .
    scanners: vuln
    severity: CRITICAL
    exit-code: "1"
    ignore-unfixed: true
```

A preceding step lists `HIGH` findings in the log without failing the build, for visibility.

Notes:

- Trivy reports severity levels `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL`. It has no separate "blocker" level, so the strictest level, `CRITICAL`, is treated as the blocker threshold.
- `ignore-unfixed: true` avoids failing on vulnerabilities that have no available fix yet, since the team cannot act on them.
- Any vulnerability suppression must be recorded in `.trivyignore` with a written justification.

### Proof that the gate works

To demonstrate the gate, a branch was created that pins a dependency with a known critical vulnerability. The pipeline failed as expected.

> **Evidence:** _add the link to the failed workflow run and/or a screenshot here_

---

## 14. Diagrams (PlantUML)

Source files are in [`docs/`](docs/):

| Diagram | File | Shows |
|---------|------|-------|
| Sequence: submit trade | `docs/sequence-submit-trade.puml` | Request flow through API, service, and repository, including the reject paths |
| Class diagram | `docs/class-diagram.puml` | `Trade`, `TradeService`, `TradeRepository`, and the exceptions |
| State diagram | `docs/state-trade-lifecycle.puml` | Trade moving from active to expired |

To render them, use the PlantUML VS Code extension, or paste the source into [plantuml.com](https://www.plantuml.com/plantuml).

---

## 15. Project Structure

```
chronos-trade-store/
├── app/
│   ├── main.py                  # App factory: wiring, lifecycle, mounts the routers
│   ├── routers/
│   │   ├── submit_trades.py     # Section: POST /trades, POST /trades/bulk
│   │   ├── read_trades.py       # Section: GET /trades, /trades/{id}, /trades/{id}/versions/{v}
│   │   ├── scheduler_status.py  # Section: GET /scheduler/status
│   │   └── tags.py              # Section names shown in Swagger
│   ├── dependencies.py          # Shared dependencies (service per request)
│   ├── errors.py                # Domain exception to HTTP status mapping
│   ├── config.py                # Environment-based configuration
│   ├── database.py              # Engine construction
│   ├── models.py                # SQLAlchemy model
│   ├── domain.py                # Trade domain object
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── repository.py            # Database access
│   ├── services.py              # Business rules
│   ├── exceptions.py            # Domain exceptions
│   ├── clock.py                 # Injectable UTC clock, IST conversion
│   └── scheduler.py             # Expiry job, run monitor, status builder
├── tests/
│   ├── conftest.py              # Fixtures, fake clock
│   ├── test_clock.py
│   ├── test_schemas.py
│   ├── test_repository.py
│   ├── test_services.py
│   ├── test_scheduler.py
│   ├── test_api.py
│   ├── test_api_scheduler_status.py
│   └── test_openapi_sections.py
├── sample_test_data/                   # Sample trades (JSON) for trying the API
├── docs/                        # PlantUML diagrams
├── .github/workflows/ci.yml
├── Dockerfile
├── requirements.txt             # Runtime dependencies (pinned)
├── requirements-dev.txt         # Test dependencies
├── pytest.ini
├── .trivyignore                 # Justified vulnerability suppressions (empty by default)
└── README.md
```

---

## 16. Known Limitations

- **No authentication or authorisation** (A16).
- **SQLite default** is suited to development. Use PostgreSQL or similar for real concurrent load.
- **Version check is read-then-write.** Two requests carrying *different* versions of the same trade at the very same instant can both pass the lower-version check, because the primary key only stops identical (`trade_id`, `version`) pairs. A per-trade lock (for example `SELECT ... FOR UPDATE` on PostgreSQL) would close this gap.
- **Replacing a same-version record overwrites it** with no audit trail of the previous values.
- **Expiry granularity is by date**, not time of day. A trade is expired from the day after its maturity date.
- **Bulk endpoint is synchronous.** Very large batches could be slow within one request, and each trade is committed separately.
- **List endpoints are not paginated.**
- **Single-instance scheduler.** If the API runs on several instances, each would run the expiry job. It is idempotent, so this is safe but redundant.
- **Scheduler status is per process and in memory.** It resets on restart, and with several instances each reports only its own runs. A shared store (a database table or metrics system) would fix this.

---

## 17. Future Improvements

- Add authentication (API keys or OAuth2)
- Add per-trade locking to close the concurrent-version gap, and an audit table for replaced records
- Ingest trades through a message queue (Kafka, RabbitMQ) for high-volume and asynchronous transmission
- Move the expiry job to a dedicated worker or database-level scheduled task, and persist its run history
- Add pagination and richer filtering to list endpoints
- Add structured logging, metrics, and tracing
- Add a CD stage that deploys the Docker image to a hosting environment

---

## Author

Vishrut Kulkarni