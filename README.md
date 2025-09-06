AI Bunko Reader (MVP)

This repository contains the MVP backend skeleton following the latest requirements in `docs/requirements.md`.

- Stack: FastAPI (Python), SQLAlchemy, PostgreSQL (pgvector), Firebase Auth
- Deploy target: Cloud Run + Cloud SQL + Cloud Storage + Cloud Tasks + Vertex AI (single environment)

Structure
- `apps/api`: FastAPI app and routers for `/v1/*`
- `apps/api/security/auth.py`: Firebase Auth verification dependency
- `apps/api/models`: SQLAlchemy ORM models (placeholders for vector columns)
- `db/schema.sql`: Raw SQL to create all tables, extensions, and indexes
- `workers/generator`: Stub for image/video generation jobs
- `ingestor/aozora`: Stub for Aozora ingestion pipeline

Setup (local)
1. Python env and deps
   - `python -m venv .venv && source .venv/bin/activate`
   - `pip install -r requirements.txt`
2. Configure env
   - Copy `.env.example` to `.env` and edit values (or export env vars)
3. Database schema (raw SQL)
   - Ensure PostgreSQL is reachable
   - Set `PSQL_URL` in your environment (see `.env.example`)
   - Apply schema: `make db-apply`
4. Run API
   - `make run-api` and open `http://localhost:8000/healthz`

Auth
- Firebase Auth tokens are verified by default.
- For local dev, you can set `AUTH_DISABLED=true` to bypass authentication.

Notes
- Vector columns (`paragraphs.embed`, `tastes.vector`) are created as `vector` in `db/schema.sql` (requires `pgvector`). ORM currently uses generic JSON placeholders; we can add `sqlalchemy-pgvector` later for strong typing.
- Generation and embedding logic are stubs; connect to Vertex AI and Cloud Tasks in subsequent steps.

Next
- Implement Librarian (hybrid search) and Recommender logic
- Connect Cloud Tasks and job status persistence
- Add embedding worker and ingestion CLI
