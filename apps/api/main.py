import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from .db.session import engine
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dotenv import load_dotenv

load_dotenv()

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

# Redirect root to login page
@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/web/index.html")


@app.get("/healthz/db")
def healthz_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/firebase-config.json", include_in_schema=False)
def firebase_config():
    cfg = {
        "apiKey": os.getenv("FIREBASE_API_KEY"),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
        "projectId": os.getenv("FIREBASE_PROJECT_ID"),
        "appId": os.getenv("FIREBASE_APP_ID"),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
        "measurementId": os.getenv("FIREBASE_MEASUREMENT_ID"),
    }
    # apiKey と projectId が無い場合は未設定とみなす
    if not cfg["apiKey"] or not cfg["projectId"]:
        raise HTTPException(status_code=404, detail="Firebase config not configured")
    return cfg
