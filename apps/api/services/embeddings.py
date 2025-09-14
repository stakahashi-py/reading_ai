import os
from typing import Optional, List, Any

EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
PROJECT_ID = os.getenv("PROJECT_ID")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "asia-northeast1")

_client: Optional[Any] = None


def get_client():
    global _client
    if _client is None:
        from google import genai  # lazy import

        _client = genai.Client(
            vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION
        )
    return _client


def embed_text(text: str) -> Optional[List[float]]:
    """Return embedding vector for text, or None on failure."""
    try:
        resp = get_client().models.embed_content(model=EMBED_MODEL, contents=[text])
        # google-genai returns .embeddings[0].values or .data depending on version; try common fields
        if hasattr(resp, "embeddings") and resp.embeddings:
            vec = resp.embeddings[0].values
        elif hasattr(resp, "data") and resp.data:
            vec = resp.data[0]["embedding"]["values"]
        else:
            return None
        return list(vec)
    except Exception:
        return None
