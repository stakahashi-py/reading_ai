import os
import time
from typing import Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ...security.auth import get_current_user
from ...db.session import get_db, SessionLocal
from ...models.models import GenerationJob

router = APIRouter()


PROJECT_ID = os.getenv("PROJECT_ID")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
ASSETS_BUCKET = os.getenv("ASSETS_BUCKET")
ASSETS_URL_PREFIX = os.getenv(
    "ASSETS_URL_PREFIX"
)  # e.g., https://storage.googleapis.com/<bucket>
VEO_MODEL_ID = os.getenv("VEO_MODEL_ID", "veo-3.0-fast-generate-001")


def _auth_headers() -> Tuple[str, dict]:
    base = f"https://{VERTEX_LOCATION}-aiplatform.googleapis.com"
    # Prefer ADC (OAuth); fallback to API key
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        return base, {}
    try:
        import google.auth
        import google.auth.transport.requests

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)
        return base, {"Authorization": f"Bearer {creds.token}"}
    except Exception:
        # last resort: require API key
        return base, {}


def _imagen_generate_uri(
    prompt: str, style: Optional[str], aspect: Optional[str]
) -> str:
    """Generate image via Vertex SDK to GCS and return its URI (gs:// or public URL)."""
    if not ASSETS_BUCKET:
        raise HTTPException(
            status_code=500, detail="ASSETS_BUCKET must be set for output_gcs_uri"
        )
    import vertexai  # type: ignore
    from vertexai.preview.vision_models import ImageGenerationModel  # type: ignore

    vertexai.init(project=PROJECT_ID, location=VERTEX_LOCATION)
    model = ImageGenerationModel.from_pretrained("imagen-4.0-generate-001")
    final_prompt = prompt if not style else f"{prompt}\n\nスタイル: {style}"
    kwargs = {
        "number_of_images": 1,
        "language": "ja",
        "person_generation": "allow_all",
        "output_gcs_uri": f"gs://{ASSETS_BUCKET.rstrip('/')}/imagen",
    }
    if aspect:
        kwargs["aspect_ratio"] = aspect
    images = model.generate_images(prompt=final_prompt, **kwargs)
    img0 = images[0]
    # Try to extract GCS URI from returned object
    uri = img0._gcs_uri
    return _to_public_url(uri)
    # except Exception:
    #     # Fallback to REST
    #     base, headers = _auth_headers()
    #     url = f"{base}/v1/projects/{PROJECT_ID}/locations/{VERTEX_LOCATION}/publishers/google/models/imagen-3.0:generateImages"
    #     body = {
    #         "prompt": prompt if not style else f"{prompt}\n\nスタイル: {style}",
    #         "numberOfImages": 1,
    #         "outputMimeType": "image/png",
    #         "size": "1024x1024",
    #     }
    #     if aspect:
    #         body["aspectRatio"] = aspect
    #     params = {}
    #     if os.getenv("GOOGLE_API_KEY"):
    #         params["key"] = os.getenv("GOOGLE_API_KEY")
    #     with httpx.Client(timeout=60) as client:
    #         r = client.post(url, headers=headers, params=params, json=body)
    #         if r.status_code >= 300:
    #             raise HTTPException(
    #                 status_code=502, detail=f"Imagen error: {r.text[:200]}"
    #             )
    #         data = r.json()
    #         b64 = None
    #         if isinstance(data, dict):
    #             if "images" in data and data["images"]:
    #                 img0 = data["images"][0]
    #                 if isinstance(img0, dict):
    #                     b64 = img0.get("bytesBase64Encoded") or (
    #                         img0.get("rawImage") or {}
    #                     ).get("bytesBase64Encoded")
    #             elif "predictions" in data and data["predictions"]:
    #                 pred0 = data["predictions"][0]
    #                 b64 = pred0.get("bytesBase64Encoded")
    #         if not b64:
    #             raise HTTPException(
    #                 status_code=502, detail="Imagen response missing image bytes"
    #             )
    #         try:
    #             return base64.b64decode(b64), "image/png"
    #         except Exception:
    #             raise HTTPException(
    #                 status_code=502, detail="Invalid base64 in Imagen response"
    #             )


def _veo_generate_and_wait(
    prompt: str, style: Optional[str], aspect: Optional[str], timeout_s: int = 180
) -> dict:
    base, headers = _auth_headers()
    gen_url = f"{base}/v1/projects/{PROJECT_ID}/locations/{VERTEX_LOCATION}/publishers/google/models/{VEO_MODEL_ID}:predictLongRunning"
    body = {
        "instances": [
            {
                "prompt": prompt if not style else f"{prompt}\n\nスタイル: {style}",
            }
        ],
        "parameters": {
            "durationSeconds": 8,
            "aspectRatio": aspect if aspect else "16:9",
            "resolution": "720p",
            "personGeneration": "allow_all",
            "sampleCount": 1,
            "storageUri": f"gs://{ASSETS_BUCKET.rstrip('/')}/veo",
        },
    }
    params = {}
    if os.getenv("GOOGLE_API_KEY"):
        params["key"] = os.getenv("GOOGLE_API_KEY")
    with httpx.Client(timeout=60) as client:
        r = client.post(gen_url, headers=headers, params=params, json=body)
        if r.status_code >= 300:
            raise HTTPException(
                status_code=502, detail=f"Veo submit error: {r.text[:200]}"
            )
        op = r.json()
        name = op.get("name")
        print(name)
        if not name:
            raise HTTPException(status_code=502, detail="Veo operation name missing")
        op_url = f"{base}/v1/projects/{PROJECT_ID}/locations/{VERTEX_LOCATION}/publishers/google/models/{VEO_MODEL_ID}/:fetchPredictOperation"
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            rr = client.post(
                op_url,
                headers=headers,
                params=params,
                json={"operationName": name},
            )
            if rr.status_code >= 300:
                raise HTTPException(
                    status_code=502, detail=f"Veo poll error: {rr.text[:200]}"
                )
            od = rr.json()
            if od.get("done"):
                return od
            time.sleep(2)
        raise HTTPException(status_code=504, detail="Veo polling timeout")


def _to_public_url(uri: str) -> str:
    if uri.startswith("gs://"):
        # translate gs://bucket/obj to prefix/obj if configured
        if ASSETS_URL_PREFIX and uri.startswith(f"gs://{ASSETS_BUCKET}/"):
            obj = uri[len(f"gs://{ASSETS_BUCKET}/") :]
            return f"{ASSETS_URL_PREFIX.rstrip('/')}/{obj}"
        # default to storage.googleapis.com
        try:
            if uri.startswith("gs://"):
                _, rest = uri.split("gs://", 1)
                bucket, obj = rest.split("/", 1)
                return f"https://storage.googleapis.com/{bucket}/{obj}"
        except Exception:
            pass
        return uri
    return uri


@router.post("/image")
def generate_image(
    payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    book_id = payload.get("book_id")
    source = payload.get("source")  # selected text or paragraph
    style = payload.get("style")
    aspect = payload.get("aspect")
    if not (book_id and source):
        raise HTTPException(status_code=400, detail="book_id and source are required")
    # Record audit
    job = GenerationJob(
        user_id=user["uid"],
        job_type="image",
        status="running",
        book_id=book_id,
        prompt=source,
        payload={"style": style, "aspect": aspect},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    url = _imagen_generate_uri(source, style, aspect)
    print("Generated image URL:", url)
    job.status = "succeeded"
    job.result = {"asset_url": url}
    db.add(job)
    db.commit()
    return {"asset_url": url}


@router.post("/video")
def generate_video(
    payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    book_id = payload.get("book_id")
    source = payload.get("source")
    style = payload.get("style")
    aspect = payload.get("aspect")
    if not (book_id and source):
        raise HTTPException(status_code=400, detail="book_id and source are required")
    job = GenerationJob(
        user_id=user["uid"],
        job_type="video",
        status="running",
        book_id=book_id,
        prompt=source,
        payload={"style": style, "aspect": aspect},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result = _veo_generate_and_wait(source, style, aspect)
    # extract uris robustly
    uris: list[str] = []
    if isinstance(result, dict):
        out = result.get("response") or result.get("result") or result
        if isinstance(out, dict):
            videos = out.get("videos")
            if isinstance(videos, list):
                for v in videos:
                    if isinstance(v, dict):
                        u = v.get("gcsUri") or v.get("uri") or v.get("storageUri")
                        if isinstance(u, str) and u:
                            uris.append(u)
            if not uris:
                ulist = out.get("videoUris") or out.get("uris")
                if isinstance(ulist, str):
                    uris = [ulist]
                elif isinstance(ulist, list):
                    uris = [u for u in ulist if isinstance(u, str)]
    public = [_to_public_url(u) for u in uris]
    primary = public[0] if public else None
    job.status = "succeeded"
    job.result = {"video_uris": public, "raw": result}
    db.add(job)
    db.commit()
    return {"asset_url": primary, "video_uris": public, "done": True}


@router.get("/{job_id}/status")
def job_status(
    job_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    job = db.get(GenerationJob, job_id)
    if not job or job.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job.id, "status": job.status, "result": job.result}
