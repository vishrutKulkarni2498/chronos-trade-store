# Chronos Trade Store

[![CI](https://github.com/<your-username>/<your-repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-username>/<your-repo>/actions/workflows/ci.yml)

A resilient Python REST API trade store enforcing versioning rules, maturity date validations, and scheduled auto-expiry with DevSecOps CI/CD pipelines. It was developed using **Test-Driven Development (TDD)** and ships with a **GitHub Actions** pipeline that runs regression tests and an **open-source vulnerability scan** which fails the build on critical vulnerabilities.

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
9. [Running the Tests](#9-running-the-tests)
10. [Test-Driven Development Approach](#10-test-driven-development-approach)
11. [CI/CD Pipeline](#11-cicd-pipeline)
12. [Vulnerability Scanning](#12-vulnerability-scanning)
13. [Diagrams (PlantUML)](#13-diagrams-plantuml)
14. [Project Structure](#14-project-structure)
15. [Known Limitations](#15-known-limitations)
16. [Future Improvements](#16-future-improvements)

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
| **A9** | Created date | `created_date` is **set by the server** at receipt time, not supplied by the client. | The sample shows `<today date>` for new trades. Trusting a client-supplied audit date is unsafe. When a same-version trade replaces a record, `created_date` is preserved from the original. |
| **A10** | Date format | The API accepts and returns **ISO 8601** (`YYYY-MM-DD`). The `dd/MM/yyyy` format in the brief is a presentation format only. | ISO 8601 is unambiguous and a standard for APIs. |
| **A11** | Field validation | `trade_id`, `counter_party_id`, and `portfolio_id` are **required, non-empty strings**. `version` is a **positive integer** (≥ 1). `maturity_date` is a valid date. | Invalid input should fail fast with a clear error. |
| **A12** | "Version: 1.1" in the brief | Refers to the version of the **case study document**, not a trade attribute. | Not part of the trade schema. |
| **A13** | "Any method of transmission" | The business logic lives in a **service layer independent of transport**. REST is the entry point implemented here, and a bulk endpoint supports high-volume ingestion. Other transports (a queue consumer, file loader) could call the same service. | Keeps the rules in one place regardless of how trades arrive. |
| **A14** | Persistence | **SQL** (SQLAlchemy). **SQLite** is the default for local runs and tests. Any SQLAlchemy-supported database (for example PostgreSQL) can be used via configuration. | The composite key and version queries suit a relational model. |
| **A15** | Concurrency | Uniqueness of (`trade_id`, `version`) is enforced by a **database constraint**, and writes occur inside a **transaction**. | Prevents duplicate rows if two identical requests arrive at the same moment. |
| **A16** | Authentication | **Not implemented.** The API is open. | Out of scope for this assignment. See [Future Improvements](#16-future-improvements). |

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
Client ──► API layer (FastAPI routes, request/response schemas)
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
```

| Layer | Responsibility |
|-------|----------------|
| **API** | HTTP concerns: routing, status codes, mapping domain exceptions to HTTP errors |
| **Service** | All business validation: version rules, maturity rules, expiry |
| **Repository** | Persistence only, with no business logic |
| **Scheduler** | Periodically triggers the expiry operation in the service layer |

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
- **Index:** on `trade_id` (fast lookup of the highest version)
- **Index:** on `maturity_date` (efficient expiry sweep)

---

## 7. API Reference

Interactive documentation is generated automatically when the app is running:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### `POST /trades`: submit a trade

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
  "created_date": "2026-09-30",
  "expired": false
}
```

**Error body**
```json
{ "detail": "Trade T2 version 1 is lower than existing version 2." }
```

### `POST /trades/bulk`: submit many trades

Accepts a JSON array of trades. Each trade is validated independently, and the response reports per-trade results (accepted or rejected with a reason), so one bad trade doesn't block the rest.

### `GET /trades`: list trades

Returns all stored trades, ordered by `trade_id` then `version`. Optional filter: `?expired=true|false`.

### `GET /trades/{trade_id}`: list all versions of a trade

Returns every stored version. `404` if the trade doesn't exist.

### `GET /trades/{trade_id}/versions/{version}`: get one version

Returns a single (`trade_id`, `version`). `404` if not found.

### `GET /health`: health check

Returns `{"status": "ok"}`.

---

## 8. Getting Started

### Prerequisites

- Python 3.11 or newer
- Git
- (Optional) Docker

### Local setup

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
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
```

---

## 9. Running the Tests

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=app --cov-report=term-missing

# Enforce the coverage threshold used in CI
pytest --cov=app --cov-fail-under=90
```

The tests use an isolated in-memory database and a frozen clock (`freezegun`), so they are deterministic and independent of the current date.

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
| Missing or empty fields are rejected | A11 |
| Invalid version (0, negative) and invalid date are rejected | A11 |
| HTTP status codes map correctly (200, 201, 404, 409, 422) | API contract |
| Bulk endpoint reports per-trade success and failure | A13 |

---

## 10. Test-Driven Development Approach

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

Build order: domain rules and service tests, then the repository, then API endpoints, then the scheduler, then the pipeline.

---

## 11. CI/CD Pipeline

The pipeline is defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) and runs on every **push** and **pull request**.

| Stage | Purpose | Fails the build when |
|-------|---------|----------------------|
| **1. Checkout and set up Python** | Prepare the environment | Setup fails |
| **2. Install dependencies** | Reproducible install from `requirements.txt` | Install fails |
| **3. Regression tests** | Run the full pytest suite with coverage | Any test fails, or coverage is below 90% |
| **4. Vulnerability scan** | Scan dependencies for known OSS vulnerabilities | Any **CRITICAL** vulnerability is found |
| **5. Docker build** | Verify the image builds | Build fails |

Because the whole suite runs on every change, it acts as an automated **regression test** gate.

---

## 12. Vulnerability Scanning

**Tool:** [Trivy](https://github.com/aquasecurity/trivy), run through `aquasecurity/trivy-action`.

**Policy:** the build **fails** when a vulnerability of `CRITICAL` severity is detected in the project's dependencies.

Relevant configuration:

```yaml
- name: OSS vulnerability scan
  uses: aquasecurity/trivy-action@master
  with:
    scan-type: fs
    scan-ref: .
    severity: CRITICAL
    exit-code: 1
    ignore-unfixed: true
```

Notes:

- Trivy reports severity levels `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL`. It has no separate "blocker" level, so the strictest level, `CRITICAL`, is treated as the blocker threshold.
- `ignore-unfixed: true` avoids failing on vulnerabilities that have no available fix yet, since the team cannot act on them.
- Any vulnerability suppression must be recorded in `.trivyignore` with a written justification.

### Proof that the gate works

To demonstrate the gate, a branch was created that pins a dependency with a known critical vulnerability. The pipeline failed as expected.

> **Evidence:** _add the link to the failed workflow run and/or a screenshot here_

---

## 13. Diagrams (PlantUML)

Source files are in [`docs/`](docs/):

| Diagram | File | Shows |
|---------|------|-------|
| Sequence: submit trade | `docs/sequence-submit-trade.puml` | Request flow through API, service, and repository, including the reject paths |
| Class diagram | `docs/class-diagram.puml` | `Trade`, `TradeService`, `TradeRepository`, and the exceptions |
| State diagram | `docs/state-trade-lifecycle.puml` | Trade moving from active to expired |

To render them, use the PlantUML VS Code extension, or paste the source into [plantuml.com](https://www.plantuml.com/plantuml).

---

## 14. Project Structure

```
trade-store/
├── app/
│   ├── main.py            # FastAPI app and route wiring
│   ├── models.py          # SQLAlchemy models
│   ├── schemas.py         # Pydantic request/response schemas
│   ├── repository.py      # Database access
│   ├── services.py        # Business rules
│   ├── exceptions.py      # Domain exceptions
│   ├── clock.py           # Injectable clock
│   └── scheduler.py       # Expiry job
├── tests/
│   ├── test_services.py
│   ├── test_repository.py
│   ├── test_api.py
│   └── test_scheduler.py
├── docs/                  # PlantUML diagrams
├── .github/workflows/ci.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## 15. Known Limitations

- **No authentication or authorisation** (A16).
- **SQLite default** is suited to development. Use PostgreSQL or similar for real concurrent load.
- **Expiry granularity is by date**, not time of day. A trade is expired from the day after its maturity date.
- **Bulk endpoint is synchronous.** Very large batches could be slow within one request.
- **Single-instance scheduler.** If the API runs on several instances, each would run the expiry job. It is idempotent, so this is safe but redundant.

---

## 16. Future Improvements

- Add authentication (API keys or OAuth2)
- Ingest trades through a message queue (Kafka, RabbitMQ) for high-volume and asynchronous transmission
- Move the expiry job to a dedicated worker or database-level scheduled task
- Add pagination and richer filtering to list endpoints
- Add structured logging, metrics, and tracing
- Add database migrations (Alembic)
- Add a CD stage that deploys the Docker image to a hosting environment

---

## Author

`Vishrut Kulkarni`, `vishrutkulkarni1002@gmail.com`