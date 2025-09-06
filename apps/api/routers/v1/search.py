from fastapi import APIRouter

router = APIRouter()


@router.post("/llm")
def llm_search(payload: dict):
    # TODO: Librarian strategy selection and fused ranking
    return {"items": [], "method_weights": {"vector": 0.0, "meta": 0.0, "title": 0.0, "bm25": 0.0}, "query": payload.get("query")}

