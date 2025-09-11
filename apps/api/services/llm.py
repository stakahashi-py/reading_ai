import os
import time
from typing import Optional, Any, Iterable, List, Dict
from google import genai

LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-pro")
PROJECT_ID = os.getenv("PROJECT_ID")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "asia-northeast1")

_client: Optional[Any] = None
_client_banana: Optional[Any] = None


def get_client():
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION
        )
    return _client


def get_client_for_nano_banana():
    global _client_banana
    if _client_banana is None:
        _client_banana = genai.Client(
            vertexai=True, project=PROJECT_ID, location="global"
        )
    return _client_banana


def translate_paragraph(book_title: str, paragraph: str) -> tuple[str, int]:
    """
    Translate a paragraph into modern Japanese. Returns (translation, latency_ms).
    """
    start = time.time()
    prompt = (
        "あなたは古典作品を現代日本語に訳す編集者です。\n"
        "- 高校教育レベルの、平易で自然な日本語にしてください。\n"
        f"作品名: {book_title}\n"
        "--- 段落 ---\n"
        f"{paragraph}\n"
        "--- 出力 ---\n"
        "現代語訳のみを出力してください。"
    )
    resp = get_client().models.generate_content(
        model="gemini-2.5-flash-lite", contents=[prompt]
    )
    text = (resp.text or "").strip()
    latency_ms = int((time.time() - start) * 1000)
    return text, latency_ms


def _trim(s: str, max_chars: int) -> str:
    if not s:
        return ""
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1] + "…"


def _build_system_instruction(book_title: str, context: Optional[str]) -> str:
    ctx = _trim((context or "").strip(), 3000)
    base = (
        "あなたは文学解説者です。以下の作品に関する質問に、平易な日本語で簡潔に答えてください。\n"
        "- 重大なネタバレは避け、必要な場合は注意書きを入れてください。\n"
        "- ユーザーが質問にあたり指定した本文は、「指定文脈」欄に記載されています。\n"
        f"作品名: {book_title}"
    )
    if ctx:
        base += "\n指定文脈:\n" + ctx
    return base


def _map_role(role: str) -> str:
    # Geminiはassistantではなくmodelロールを使用
    return "model" if role.lower() in ("assistant", "model") else "user"


def _build_contents(
    history: Optional[List[Dict[str, str]]], question: str
) -> List[Dict[str, object]]:
    contents: List[Dict[str, object]] = []
    if history:
        for msg in history:
            role = _map_role(str(msg.get("role") or "user"))
            content = _trim((msg.get("content") or "").strip(), 1000)
            if not content:
                continue
            contents.append({"role": role, "parts": [{"text": content}]})
    contents.append({"role": "user", "parts": [{"text": _trim(question, 2000)}]})
    return contents


def answer_question(
    book_title: str,
    question: str,
    context: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> tuple[str, int]:
    """Answer a user question with optional context and chat history using role-based messages."""
    start = time.time()
    system_instruction = _build_system_instruction(book_title, context)
    contents = _build_contents(history, question)
    grounding_tool = genai.types.Tool(google_search=genai.types.GoogleSearch())
    resp = get_client().models.generate_content(
        model=LLM_MODEL,
        contents=contents,
        config={
            "tools": [grounding_tool],
            "system_instruction": system_instruction,
        },
    )
    text = (resp.text or "").strip()
    latency_ms = int((time.time() - start) * 1000)
    return text, latency_ms


# def stream_answer_question(
#     book_title: str,
#     question: str,
#     context: Optional[str] = None,
#     history: Optional[List[Dict[str, str]]] = None,
# ) -> Iterable[str]:
#     """Yield answer chunks (context/history-aware) using role-based messages. Fallback to non-streaming when unavailable."""
#     # try:
#     client = get_client()
#     system_instruction = _build_system_instruction(book_title, context)
#     contents = _build_contents(history, question)
#     # google genai streaming API（利用可なら）
#     grounding_tool = genai.types.Tool(google_search=genai.types.GoogleSearch())
#     stream = client.models.generate_content_stream(
#         model=LLM_MODEL,
#         contents=contents,
#         config={
#             "tools": [grounding_tool],
#             "system_instruction": system_instruction,
#         },
#     )
#     for chunk in stream:
#         try:
#             yield chunk.text
#         except Exception:
#             continue
#     return
# except Exception:
#     yield "[エラー] 回答の生成に失敗しました。"
# # Fallback: non-streaming → 擬似チャンク
# text, _ = answer_question(book_title, question, context=context, history=history)
# step = 60
# for i in range(0, len(text), step):
#     yield text[i : i + step]
