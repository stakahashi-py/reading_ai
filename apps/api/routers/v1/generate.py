from fastapi import APIRouter, Depends

from ...security.auth import get_current_user

router = APIRouter()


@router.post("/image")
def generate_image(payload: dict, user=Depends(get_current_user)):
    # TODO: enqueue Cloud Tasks job and return job_id
    return {"job_id": "job_demo"}


@router.post("/video")
def generate_video(payload: dict, user=Depends(get_current_user)):
    # TODO: enqueue Cloud Tasks job and return job_id
    return {"job_id": "job_demo"}


@router.get("/{job_id}/status")
def job_status(job_id: str, user=Depends(get_current_user)):
    # TODO: check job status from DB/Redis
    return {"job_id": job_id, "status": "queued"}

