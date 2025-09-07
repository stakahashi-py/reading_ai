from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any, List, Optional, Tuple

from ...db.session import get_db
from ...services.embeddings import embed_text

router = APIRouter()


def _rows_to_books(db: Session, ids: List[int]) -> List[Dict[str, Any]]:
    if not ids:
        return []
    rows = db.execute(text("SELECT id, title, author, era, tags FROM books WHERE id = ANY(:ids)"), {"ids": ids}).fetchall()
    by_id = {r[0]: {"id": r[0], "title": r[1], "author": r[2], "era": r[3], "tags": r[4]} for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def _pick_best(snippets: Dict[int, Tuple[float, str]]) -> Dict[int, str]:
    """Return per-book best snippet chosen by highest partial score."""
    out: Dict[int, str] = {}
    for bid, (_score, snip) in snippets.items():
        out[bid] = snip
    return out


@router.post("/llm")
def llm_search(payload: dict, db: Session = Depends(get_db)):
    q: str = (payload.get("query") or "").strip()
    limit: int = int(payload.get("limit") or 10)
    offset: int = int(payload.get("offset") or 0)
    author_filter = payload.get("author")
    era_filter = payload.get("era")
    tag_filter = payload.get("tag") or payload.get("genre")

    method_weights = {"vector": 0.6, "title": 0.35, "keyword": 0.05}

    # helpers to build WHERE fragments with correct aliasing
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

    # 1) title/author trigram similarity
    sql_title = """
      SELECT id, GREATEST(similarity(title, :q), similarity(author, :q)) AS score
      FROM books
      WHERE (title ILIKE :pat OR author ILIKE :pat)
      {era}{author}{tag}
      ORDER BY score DESC
      LIMIT :lim
    """
    rows_title = db.execute(
        text(sql_title.format(era=w_era(None), author=w_author(None), tag=w_tag(None))),
        {"q": q, "pat": f"%{q}%", "lim": limit, "era": era_filter, "af": f"%{author_filter}%" if author_filter else None, "tag": tag_filter},
    ).fetchall()

    # 2) keyword paragraph match (simple ILIKE)
    sql_kw = """
      SELECT p.book_id, MAX(1.0) AS score
      FROM paragraphs p
      JOIN books b ON b.id = p.book_id
      WHERE p.text ILIKE :pat
      {era}
      {author}
      {tag}
      GROUP BY p.book_id
      ORDER BY MAX(1.0) DESC
      LIMIT :lim
    """
    # keyword top paragraphs (for snippet)
    sql_kw_p = """
      SELECT p.book_id, p.id, p.text, 1.0 AS score
      FROM paragraphs p
      JOIN books b ON b.id = p.book_id
      WHERE p.text ILIKE :pat
      {era}{author}{tag}
      ORDER BY p.id ASC
      LIMIT :lim
    """
    rows_kw_p = db.execute(
        text(sql_kw_p.format(era=w_era('b'), author=w_author('b'), tag=w_tag('b'))),
        {"pat": f"%{q}%", "lim": limit * 5, "era": era_filter, "af": f"%{author_filter}%" if author_filter else None, "tag": tag_filter},
    ).fetchall()

    # 3) vector search via paragraphs.embed (pgvector)
    vec = embed_text(q)
    rows_vec = []
    rows_vec_p = []
    if vec is not None:
        sql_vec_p = """
          SELECT p.book_id, p.id, p.text, (p.embed <-> :qvec) AS dist
          FROM paragraphs p
          JOIN books b ON b.id = p.book_id
          WHERE 1=1{era}{author}{tag}
          ORDER BY dist ASC
          LIMIT :lim
        """
        rows_vec_p = db.execute(
            text(sql_vec_p.format(era=w_era('b'), author=w_author('b'), tag=w_tag('b'))),
            {"qvec": vec, "lim": limit * 5, "era": era_filter, "af": f"%{author_filter}%" if author_filter else None, "tag": tag_filter},
        ).fetchall()
        # aggregate vector distances by book
        dists: Dict[int, float] = {}
        for r in rows_vec_p:
            bid = r[0]
            dist = float(r[3])
            if bid not in dists or dist < dists[bid]:
                dists[bid] = dist
        rows_vec = [(bid, d) for bid, d in dists.items()]

    # Fuse results
    scores: Dict[int, float] = {}
    # keep best snippet per book using partial score
    best_snippet: Dict[int, Tuple[float, str]] = {}
    def add_scores(rows, weight, value_is_distance=False):
        for r in rows:
            book_id = r[0]
            val = float(r[1])
            score = (1.0 / (1.0 + val)) if value_is_distance else val
            scores[book_id] = scores.get(book_id, 0.0) + weight * score

    # Title/author similarity
    add_scores(rows_title, method_weights["title"])
    # Keyword paragraphs snippets
    for r in rows_kw_p:
        bid, _pid, ptext, kw_score = r[0], r[1], r[2], float(r[3])
        partial = method_weights["keyword"] * kw_score
        if bid not in scores:
            scores[bid] = 0.0
        # store snippet (first hit) if better
        if (bid not in best_snippet) or (partial > best_snippet[bid][0]):
            best_snippet[bid] = (partial, ptext)
        scores[bid] += partial
    if rows_vec:
        add_scores(rows_vec, method_weights["vector"], value_is_distance=True)
        # choose best vector paragraph as snippet
        for r in rows_vec_p:
            bid, _pid, ptext, dist = r[0], r[1], r[2], float(r[3])
            part = method_weights["vector"] * (1.0 / (1.0 + dist))
            if (bid not in best_snippet) or (part > best_snippet[bid][0]):
                best_snippet[bid] = (part, ptext)

    # Rank and materialize
    ranked_all = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    total = len(ranked_all)
    ranked = ranked_all[offset: offset + limit]
    ids = [bid for bid, _ in ranked]
    items = _rows_to_books(db, ids)
    # attach score in the same order
    score_map = {bid: sc for bid, sc in ranked}
    snippet_map = _pick_best(best_snippet)
    for it in items:
        it["score"] = round(score_map.get(it["id"], 0.0), 6)
        snip = snippet_map.get(it["id"]) or ""
        # trim snippet to ~120 chars
        it["snippet"] = (snip[:120] + ("…" if len(snip) > 120 else "")) if snip else ""
    return {"items": items, "method_weights": method_weights, "query": q, "offset": offset, "limit": limit, "total": total}
