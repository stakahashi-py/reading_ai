from fastapi import APIRouter, Depends, Query
from typing import Optional

from ...security.auth import get_current_user_optional

router = APIRouter()


@router.get("")
def list_books(
    author: Optional[str] = None,
    genre: Optional[str] = None,
    era: Optional[str] = None,
    q: Optional[str] = None,
    user=Depends(get_current_user_optional),
):
    # TODO: implement filters with DB
    return {"items": [], "filters": {"author": author, "genre": genre, "era": era, "q": q}}


@router.get("/{book_id}")
def get_book(book_id: int):
    # TODO: fetch book detail
    return {"id": book_id}


@router.get("/{book_id}/paragraphs")
def get_paragraphs(book_id: int, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    # TODO: fetch paragraphs
    return {"book_id": book_id, "offset": offset, "limit": limit, "items": []}

