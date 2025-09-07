import os
import time
from typing import Optional, Any


LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
PROJECT_ID = os.getenv("PROJECT_ID")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "asia-northeast1")

_client: Optional[Any] = None


def get_client():
    global _client
    if _client is None:
        from google import genai  # lazy import
        _client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)
    return _client


def translate_paragraph(book_title: str, paragraph: str) -> tuple[str, int]:
    """
    Translate a paragraph into modern Japanese. Returns (translation, latency_ms).
    """
    start = time.time()
    prompt = (
        "あなたは古典作品を現代日本語に訳す編集者です。\n"
        "- 固有名詞は原則保持し、必要に応じてカナを補助してください。\n"
        "- 平易で自然な日本語にしてください。\n"
        f"作品名: {book_title}\n"
        "--- 段落 ---\n"
        f"{paragraph}\n"
        "--- 出力 ---\n"
        "現代語訳のみを書いてください。"
    )
    resp = get_client().models.generate_content(model=LLM_MODEL, contents=[prompt])
    text = (resp.text or "").strip()
    latency_ms = int((time.time() - start) * 1000)
    return text, latency_ms


def answer_question(book_title: str, question: str) -> tuple[str, int]:
    """Answer a user question about the work in simple Japanese (no spoilers unless necessary)."""
    start = time.time()
    prompt = (
        "あなたは文学解説者です。以下の作品についての質問に、平易な日本語で簡潔に答えてください。\n"
        "- 推測はその旨を明示し、重大なネタバレは避けてください（必要なときは注意書き）。\n"
        f"作品名: {book_title}\n"
        f"質問: {question}\n"
        "--- 出力 ---\n"
        "回答のみ。"
    )
    resp = get_client().models.generate_content(model=LLM_MODEL, contents=[prompt])
    text = (resp.text or "").strip()
    latency_ms = int((time.time() - start) * 1000)
    return text, latency_ms
