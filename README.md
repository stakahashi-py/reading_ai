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
- `web/`: Minimal static frontend (books list, reading view)

Setup (local)
1. Python env and deps
   - `python -m venv .venv && source .venv/bin/activate`
   - `pip install -r requirements.txt`
2. Configure env
   - Copy `.env.example` to `.env` and edit values (or export env vars)
3. Database schema (raw SQL)
   - Ensure PostgreSQL/Cloud SQL is reachable
   - If using Cloud SQL connector (recommended): set `.env` with `CONNECTION_NAME`, `DB_USER`, `DB_NAME`, `DB_PASS` (or IAM auth)
   - Or set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db`
   - Apply schema: `make db-apply` (or `python scripts/apply_schema.py`)
4. Run API
   - `make run-api` and open `http://localhost:8000/web/index.html`

Auth
- Firebase Auth tokens are verified by default.
- For local dev, set `AUTH_DISABLED=true` to bypass authentication. When enabled, endpoints that require auth accept missing Authorization and act as a dev user.

Notes
- Vector columns (`paragraphs.embed`, `tastes.vector`) are created as `vector` in `db/schema.sql` (requires `pgvector`). ORM currently uses generic JSON placeholders; we can add `sqlalchemy-pgvector` later for strong typing.
- Generation and embedding logic are stubs; connect to Vertex AI and Cloud Tasks in subsequent steps.
- Gemini (google-genai) backs `/v1/translate` and `/v1/qa`. Set `PROJECT_ID` and `VERTEX_LOCATION` envs for Vertex AI.

Frontend (MVP)
- Navigate to `/web/index.html` for books, then open a book to read and try:
  - Translate a selected paragraph via `/v1/translate`
  - Ask QA via `/v1/qa`
- Search UI is available at `/web/search.html` (query, author/era/tag filters). Results link to reading view.

Generation Jobs
- `POST /v1/generate/image|video` enqueues a DB job in `generation_jobs`.
- `GET /v1/generate/{job_id}/status` returns current status/result.
- Worker is a stub; connect to Vertex Imagen/Veo and update job status in a background service.

Next
- Implement Librarian (hybrid search) and Recommender logic
- Connect Cloud Tasks and job status persistence
- Add embedding worker and ingestion CLI
- DB connections
  - API uses Cloud SQL connector when `CONNECTION_NAME/DB_USER/DB_NAME` are set (driver: pg8000). Otherwise falls back to `DATABASE_URL`.
  - The ingestion script `ingest_aozora_html.py` uses the same connector style for consistency.
