from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_, text

from ...security.auth import get_current_user_optional
from ...db.session import get_db
from ...models.models import Book, Paragraph

router = APIRouter()


@router.get("")
def list_books(
    author: Optional[str] = None,
    genre: Optional[str] = None,
    era: Optional[str] = None,
    q: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    query = db.query(Book)
    if author:
        query = query.filter(Book.author.ilike(f"%{author}%"))
    if era:
        query = query.filter(Book.era == era)
    if genre:
        # interpret as tag
        query = query.filter(Book.tags.any(genre))
    if q:
        query = query.filter(or_(Book.title.ilike(f"%{q}%"), Book.author.ilike(f"%{q}%")))
    try:
        total = query.count()
        rows: List[Book] = query.order_by(Book.created_at.desc()).offset(offset).limit(limit).all()
        items = [
            {
                "id": b.id,
                "slug": b.slug,
                "title": b.title,
                "author": b.author,
                "era": b.era,
                "tags": b.tags,
                "length_chars": b.length_chars,
            }
            for b in rows
        ]
        return {"items": items, "offset": offset, "limit": limit, "total": total}
    except Exception as e:
        # Graceful fallback when DB is not reachable in dev
        return {"items": [], "offset": offset, "limit": limit, "total": 0, "error": str(e)}


@router.get("/{book_id}")
def get_book(book_id: int, db: Session = Depends(get_db)):
    b = db.get(Book, book_id)
    if not b:
        return {"error": "not found"}
    return {
        "id": b.id,
        "slug": b.slug,
        "title": b.title,
        "author": b.author,
        "era": b.era,
        "tags": b.tags,
        "length_chars": b.length_chars,
        "citation": b.citation,
    }


@router.get("/{book_id}/paragraphs")
def get_paragraphs(
    book_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        q = (
            db.query(Paragraph)
            .filter(Paragraph.book_id == book_id)
            .order_by(Paragraph.idx.asc())
        )
        total = q.count()
        rows = q.offset(offset).limit(limit).all()
        items = [
            {"id": p.id, "idx": p.idx, "text": p.text, "char_start": p.char_start, "char_end": p.char_end}
            for p in rows
        ]
        return {"book_id": book_id, "offset": offset, "limit": limit, "total": total, "items": items}
    except Exception as e:
        return {"book_id": book_id, "offset": offset, "limit": limit, "total": 0, "items": [], "error": str(e)}


@router.get("/filters")
def get_filters(db: Session = Depends(get_db)):
    # Distinct eras
    eras_rows = db.execute(text("SELECT DISTINCT era FROM books WHERE era IS NOT NULL ORDER BY era ASC")).fetchall()
    eras = [r[0] for r in eras_rows if r[0]]
    # Distinct tags via unnest
    tags_rows = db.execute(text("SELECT DISTINCT unnest(tags) AS tag FROM books WHERE tags IS NOT NULL ORDER BY tag ASC")).fetchall()
    tags = [r[0] for r in tags_rows if r[0]]
    return {"eras": eras, "tags": tags}
