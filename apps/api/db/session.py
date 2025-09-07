import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Two connection modes:
# 1) Cloud SQL Connector (preferred in GCP): use CONNECTION_NAME/DB_USER/DB_NAME/DB_PASS
# 2) Direct DATABASE_URL (local/dev): e.g. postgresql+psycopg://user:pass@host:5432/db

CONNECTION_NAME = os.getenv("CONNECTION_NAME")
DB_USER = os.getenv("DB_USER")
DB_NAME = os.getenv("DB_NAME")
DB_PASS = os.getenv("DB_PASS")

DATABASE_URL = os.getenv("DATABASE_URL")


def _create_engine():
    if CONNECTION_NAME and DB_USER and DB_NAME:
        # Cloud SQL connector via pg8000
        def getconn():
            from google.cloud.sql.connector import Connector, IPTypes  # lazy import

            connector = Connector()
            return connector.connect(
                CONNECTION_NAME,
                "pg8000",
                user=DB_USER,
                db=DB_NAME,
                password=DB_PASS,
                enable_iam_auth=True,
                ip_type=IPTypes.PUBLIC,
            )

        return create_engine(
            "postgresql+pg8000://",
            creator=getconn,
            pool_pre_ping=True,
            future=True,
        )
    # Fallback to DATABASE_URL
    url = DATABASE_URL or "postgresql+psycopg://user:pass@localhost:5432/reading"
    return create_engine(url, pool_pre_ping=True, future=True)


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
