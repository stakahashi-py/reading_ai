from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from .db.session import engine
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import api_v1 as v1

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

# Serve static web (simple MVP)
app.mount("/web", StaticFiles(directory="web", html=True), name="web")

# Redirect root to search page
@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/web/search.html")


@app.get("/healthz/db")
def healthz_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
