from fastapi import APIRouter, Body, Query
from fastapi.responses import StreamingResponse
import httpx

router = APIRouter()


# 外部 Librarian Agent のベースURL（固定でOKと確認済み）
AGENT_BASE = "https://librarian-agent-858293481093.us-central1.run.app"


@router.post("/librarian/session/init")
async def init_session(user_id: str = Query(..., description="Firebaseのuid")):
    """初回チャット時のセッション初期化（DELETE→POST）。
    ブラウザからは同一オリジンにPOSTするため、CORSプリフライトを回避。
    """
    async with httpx.AsyncClient(timeout=20.0) as client:
        # ボディ無しでOK
        try:
            await client.delete(
                f"{AGENT_BASE}/apps/librarian_agent/users/{user_id}/sessions/session"
            )
        except httpx.HTTPError:
            # 既存なし等は無視
            pass
        r = await client.post(
            f"{AGENT_BASE}/apps/librarian_agent/users/{user_id}/sessions/session"
        )
        r.raise_for_status()
    return {"ok": True}


@router.post("/librarian/run_sse")
async def proxy_run_sse(payload: dict = Body(...)):
    """/run_sse へのSSEストリームをプロキシ。
    同一オリジン→本API→外部サービス で中継し、ブラウザ側のOPTIONSエラーを回避。
    """

    async def gen():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{AGENT_BASE}/run_sse",
                headers={
                    "Accept": "text/event-stream",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as r:
                r.raise_for_status()
                async for chunk in r.aiter_raw():
                    # 外部SSEのチャンクをそのまま転送
                    if chunk:
                        yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")
