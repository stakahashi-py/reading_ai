from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any, List, Optional, Tuple

from ...db.session import get_db
from ...services.embeddings import embed_text

router = APIRouter()


def _rows_to_books(db: Session, ids: List[int]) -> List[Dict[str, Any]]:
    if not ids:
        return []
    rows = db.execute(
        text("SELECT id, title, author, era, tags FROM books WHERE id = ANY(:ids)"),
        {"ids": ids},
    ).fetchall()
    by_id = {
        r[0]: {"id": r[0], "title": r[1], "author": r[2], "era": r[3], "tags": r[4]}
        for r in rows
    }
    return [by_id[i] for i in ids if i in by_id]


@router.post("/title")
def title_search(payload: dict, db: Session = Depends(get_db)):
    """
    タイトル専用検索（ベクトル検索なし）。
    - タイトルの完全一致を優先し、その後にtrigram類似度で部分一致を並べ替え。
    - 著者・時代・タグのフィルタは維持。
    """
    q: str = (payload.get("query") or "").strip()
    limit: int = int(payload.get("limit") or 10)
    offset: int = int(payload.get("offset") or 0)
    author_filter = payload.get("author")
    era_filter = payload.get("era")
    tag_filter = payload.get("tag") or payload.get("genre")

    # WHERE句ビルダ（llm_searchと同様の挙動）
    def w_era(alias: Optional[str] = None) -> str:
        if not era_filter:
            return ""
        col = f"{alias}.era" if alias else "era"
        return f" AND {col} = :era"

    def w_author(alias: Optional[str] = None) -> str:
        if not author_filter:
            return ""
        col = f"{alias}.author" if alias else "author"
        return f" AND {col} ILIKE :af"

    def w_tag(alias: Optional[str] = None) -> str:
        if not tag_filter:
            return ""
        col = f"{alias}.tags" if alias else "tags"
        return f" AND :tag = ANY({col})"

    # 件数
    sql_cnt = text(
        (
            "SELECT COUNT(*) FROM books WHERE 1=1"
            + (" AND title ILIKE :pat" if q else "")
            + w_era(None)
            + w_author(None)
            + w_tag(None)
        )
    )
    total = (
        db.execute(
            sql_cnt,
            {
                "pat": f"%{q}%" if q else None,
                "era": era_filter,
                "af": f"%{author_filter}%" if author_filter else None,
                "tag": tag_filter,
            },
        ).scalar()
        or 0
    )

    # 本体クエリ：完全一致を最優先、次に類似度（pg_trgm）で降順
    sql = text(
        (
            """
            SELECT id,
                   CASE WHEN LOWER(title) = LOWER(:q) THEN 1 ELSE 0 END AS exact_match,
                   similarity(title, :q) AS sim
            FROM books
            WHERE 1=1
            """
            + (" AND title ILIKE :pat" if q else "")
            + w_era(None)
            + w_author(None)
            + w_tag(None)
            + " ORDER BY exact_match DESC, sim DESC, id ASC LIMIT :lim OFFSET :off"
        )
    )
    rows = db.execute(
        sql,
        {
            "q": q or "",
            "pat": f"%{q}%" if q else None,
            "era": era_filter,
            "af": f"%{author_filter}%" if author_filter else None,
            "tag": tag_filter,
            "lim": limit,
            "off": offset,
        },
    ).fetchall()

    ids = [r[0] for r in rows]
    items = _rows_to_books(db, ids)
    # スコアは表示不要のため付与しない（UI側は未定義なら非表示）
    for it in items:
        it["snippet"] = ""

    return {
        "items": items,
        "query": q,
        "offset": offset,
        "limit": limit,
        "total": int(total),
    }
