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
ENABLE_IAM_AUTH = os.getenv("ENABLE_IAM_AUTH", "false").lower() == "true"
CLOUD_SQL_IP_TYPE = (os.getenv("CLOUD_SQL_IP_TYPE", "PUBLIC") or "PUBLIC").upper()

DATABASE_URL = os.getenv("DATABASE_URL")


def _create_engine():
    if CONNECTION_NAME and DB_USER and DB_NAME:
        # Cloud SQL connector via pg8000
        def getconn():
            from google.cloud.sql.connector import Connector, IPTypes  # lazy import

            connector = Connector()
            kwargs = {
                "driver": "pg8000",
                "user": DB_USER,
                "db": DB_NAME,
                "enable_iam_auth": ENABLE_IAM_AUTH,
                "ip_type": IPTypes.PRIVATE if CLOUD_SQL_IP_TYPE == "PRIVATE" else IPTypes.PUBLIC,
            }
            # Use password only when IAM auth is disabled
            if not ENABLE_IAM_AUTH and DB_PASS:
                kwargs["password"] = DB_PASS
            return connector.connect(CONNECTION_NAME, **kwargs)

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
