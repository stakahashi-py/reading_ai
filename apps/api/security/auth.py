import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

auth_scheme = HTTPBearer(auto_error=False)

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
AUTH_DISABLED = os.getenv("AUTH_DISABLED", "false").lower() == "true"

firebase_initialized = False


def _init_firebase():
    global firebase_initialized
    if firebase_initialized:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            # If running on GCP, ADC is used; otherwise this falls back to default
            firebase_admin.initialize_app()
        firebase_initialized = True
    except Exception:
        # Defer failures to verification time
        pass


def verify_token(id_token: str) -> Optional[dict]:
    if AUTH_DISABLED:
        return {"uid": "dev-user"}
    _init_firebase()
    try:
        from firebase_admin import auth

        decoded = auth.verify_id_token(id_token, check_revoked=False)
        if FIREBASE_PROJECT_ID and decoded.get("aud") not in [FIREBASE_PROJECT_ID, f"{FIREBASE_PROJECT_ID}"]:
            raise ValueError("Invalid audience")
        return decoded
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization")
    token = credentials.credentials
    return verify_token(token)


def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme)):
    if not credentials:
        return None
    token = credentials.credentials
    try:
        return verify_token(token)
    except HTTPException:
        return None

