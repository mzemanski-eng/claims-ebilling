# Claims ALAE eBilling Platform

Purpose-built eBilling platform for Claims ALAE (Allocated Loss Adjustment Expense) vendor services. Auto-classifies supplier invoices, validates against contract rate cards and narrative guidelines, and provides fast, explainable exception resolution.

**Initial ALAE scope:** IME · Engineering · Independent Adjusting · Investigation · Record Retrieval

---

## Quick Start (Local Development)

### Prerequisites
- Python 3.12+
- Docker (for Postgres + Redis)

```bash
# 1. Clone and set up environment
git clone https://github.com/your-org/claims-ebilling
cd claims-ebilling
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 2. Configure environment
cp .env.example .env
# Edit .env if needed (defaults work with docker-compose)

# 3. Start Postgres + Redis
docker compose up -d

# 4. Run migrations + seed taxonomy
alembic upgrade head
python -m app.taxonomy.seed

# 5. Start the API (terminal 1)
uvicorn app.main:app --reload --port 8000

# 6. Start the worker (terminal 2)
rq worker --url redis://localhost:6379 invoice-pipeline
```

API docs: http://localhost:8000/docs
Health check: http://localhost:8000/health

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Project Structure

```
app/
  main.py              FastAPI app factory + lifespan
  settings.py          All config via pydantic-settings
  database.py          SQLAlchemy engine + session
  models/              ORM models (taxonomy, supplier, invoice, mapping, validation, audit)
  schemas/             Pydantic request/response models
  routers/             FastAPI route handlers (health, auth, supplier, admin)
  services/
    storage/           File storage (LocalDisk → S3 swap via env var)
    ingestion/         CSV parser + PDF stub (dispatcher)
    classification/    Rule engine + classifier orchestrator
    validation/        Rate validator + guideline validator
    mapping/           Mapping rule CRUD + versioning
    audit/             Immutable audit event logger
  workers/             RQ queue setup + invoice pipeline job
  taxonomy/            UTMSB taxonomy constants + DB seeder

alembic/               Database migrations
fixtures/              Sample invoice CSVs + rate card CSV for testing
tests/                 pytest test suite
```

---

## Deployment (Render)

This repo is Render-ready from day 1. Push to GitHub and connect via Render dashboard.

**Services defined in `render.yaml`:**
- `claims-ebilling-api` — FastAPI web service
- `claims-ebilling-worker` — RQ background worker
- `claims-ebilling-redis` — Managed Redis
- `claims-ebilling-db` — Managed Postgres

**Build command** (web service):
```
pip install -r requirements.txt && alembic upgrade head && python -m app.taxonomy.seed
```

**Start command** (web service):
```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Start command** (worker):
```
rq worker --url $REDIS_URL invoice-pipeline
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| File formats v1 | CSV only | De-risks PDF quality; PDF stubbed for v2 |
| Background jobs | RQ + Redis | Simplest Render-compatible approach |
| ORM | SQLAlchemy 2.x + Alembic | Mature ecosystem, essential migrations |
| Auth | JWT (python-jose) | Stateless; SSO/SAML when carriers require |
| Classification | Rule-based (keyword/regex) | Deterministic, auditable; ML interface designed in |
| Taxonomy codes | Never shown to suppliers | Core product principle |
| Audit log | Append-only (no UPDATE/DELETE) | Immutable for dispute resolution |

---

## v1 Scope (MVP)

- [x] CSV ingestion + normalization
- [x] UTMSB taxonomy (all 5 ALAE domains)
- [x] Rule-based classifier (keyword + regex)
- [x] Rate validation engine
- [x] Guideline validation engine (5 rule types)
- [x] Exception generation + lifecycle
- [x] Mapping rule persistence + carrier override
- [x] Audit event logging
- [x] Supplier API (upload, view results, respond to exceptions)
- [x] Carrier admin API (review, override, approve, export)
- [x] JWT auth
- [x] Render deployment config

## Deferred to v2

- [ ] PDF extraction (pdfplumber — interface wired, raises NotImplementedError)
- [ ] Email notifications (SendGrid)
- [ ] ML-assisted classification (train on confirmed mapping history)
- [ ] Guideline rule authoring UI
- [ ] Multi-carrier data isolation
- [ ] S3 file storage (interface wired; swap `STORAGE_BACKEND=s3`)
- [ ] AP system export (EDI 810)
- [ ] Analytics dashboard
