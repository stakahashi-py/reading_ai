from fastapi import FastAPI
from sqlalchemy import text
from .db.session import engine
from fastapi.middleware.cors import CORSMiddleware

from .routers import v1

app = FastAPI(title="AI Bunko Reader API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


app.include_router(v1.router, prefix="/v1")


@app.get("/healthz/db")
def healthz_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
