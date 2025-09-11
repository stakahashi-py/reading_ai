import os
import time
from typing import Optional, Tuple
from pydantic import BaseModel
import uuid
from io import BytesIO
import json

from PIL import Image
import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from google.cloud import storage
from google import genai
from google.genai import types
from sqlalchemy import text

from ...security.auth import get_current_user
from ...db.session import get_db, SessionLocal
from ...models.models import GenerationJob, Gallery
from ...services.llm import get_client_for_nano_banana as get_client

router = APIRouter()

client = get_client()

PROJECT_ID = os.getenv("PROJECT_ID")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
ASSETS_BUCKET = os.getenv("ASSETS_BUCKET")
ASSETS_URL_PREFIX = os.getenv(
    "ASSETS_URL_PREFIX"
)  # e.g., https://storage.googleapis.com/<bucket>
CHARACTER_BUCKET = os.getenv("CHARACTERS_BUCKET")
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


def _upload_to_gcs(local_path, bucket_name, gcs_path):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_path)
    print(f"Uploaded to gs://{bucket_name}/{gcs_path}")


class CharacterNames(BaseModel):
    names: list[str]


def check_characters(title, text, character_names):
    # Geminiを用いて登場人物を抽出
    system = (
        f"「{title}」の一部本文が与えられます。その中に登場する人物を特定し、JSON形式で返してください。\n"
        "- 「# 登場人物ホワイトリスト」に記載のある名前のみを候補としてください。それ以外の登場人物は出力しないでください。\n"
        f"# 本文:\n{text}"
        f"# 登場人物ホワイトリスト:\n{character_names}\n"
    )
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=system,
        config={
            "response_mime_type": "application/json",
            "response_schema": CharacterNames,
            "temperature": 0.05,
        },
    )
    return resp.text


def _generate_image_and_url(title, content, character_names) -> str:
    """Generate image via Vertex SDK to GCS and return its URI (gs:// or public URL)."""
    # プロンプトの入れ物準備
    contents = [types.Content(role="user", parts=[])]

    # テキストプロンプトの準備
    prompt_template = """Please generate an illustration of the following scene from the novel 「{title}」
- {content}

# Notes
- You don’t need to illustrate all the input scenes. From the given scenes, select only one impressive moment and make a single illustration of it.
- Do not include any text in the output. character appearance, please follow the provided images.
{characters}
- If characters appear who are not included in the provided images, generate them in a style consistent with the other characters, using your own interpretation.
"""
    characters = "\n".join(
        [f"  - Image {i}: {name}" for i, name in enumerate(character_names)]
    )
    text_prompt = prompt_template.format(
        title=title, content=content, characters=characters
    )
    # 入れ物に突っ込む
    contents[0].parts.append(types.Part.from_text(text=text_prompt))

    # 画像の準備
    for character_name in character_names:
        # Partオブジェクト作成
        image_part = types.Part.from_uri(
            file_uri=f"gs://{CHARACTER_BUCKET}/{title}/{character_name}.png",
            mime_type="image/png",
        )
        print(
            f"gs://{CHARACTER_BUCKET}/{title}/{character_name}.png",
        )
        # 入れ物に突っ込んでいく
        contents[0].parts.append(image_part)

    # 画像生成実行
    resp = client.models.generate_content(
        model="gemini-2.5-flash-image-preview",
        contents=contents,
        config={"response_modalities": ["TEXT", "IMAGE"]},
    )
    retry_count = 0
    os.makedirs("/tmp", exist_ok=True)
    local_path = f"/tmp/{uuid.uuid4().hex}.png"
    while retry_count < 3:
        for part in resp.candidates[0].content.parts:
            if part.inline_data is not None:
                image = Image.open(BytesIO(part.inline_data.data))
                image.save(local_path)
                flg = True
        if flg:
            break
        else:
            retry_count += 1
            print(f"{retry_count}回目 画像生成に失敗しました。{title}_{content[:10]}")

    # GCSにアップロード
    _upload_to_gcs(local_path, ASSETS_BUCKET, f"imagen/{os.path.basename(local_path)}")
    # URIを返す
    return _to_public_url(f"gs://{ASSETS_BUCKET}/imagen/{os.path.basename(local_path)}")


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
            "generateAudio": False,
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
    # style = payload.get("style")
    # aspect = payload.get("aspect")
    if not (book_id and source):
        raise HTTPException(status_code=400, detail="book_id and source are required")
    # Record audit
    job = GenerationJob(
        user_id=user["uid"],
        job_type="image",
        status="running",
        book_id=book_id,
        prompt=source,
        # payload={"style": style, "aspect": aspect},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    # タイトルとキャラ一覧取得
    result = db.execute(
        text("SELECT title, characters FROM books WHERE id = :bid"),
        {"bid": book_id},
    )
    row = result.mappings().first()
    title = row["title"]
    characters_json = row["characters"]
    character_names = [c["name"] for c in characters_json]
    # 出現キャラチェック
    retry_count = 0
    while retry_count < 3:
        try:
            checked_character_names_row = check_characters(
                title, source, character_names
            )
            checked_character_names = (
                json.loads(checked_character_names_row).get("names") or []
            )
            break
        except Exception as e:
            print(f"登場人物の抽出に失敗しました: {e}")
            retry_count += 1
            checked_character_names = []
    url = _generate_image_and_url(title, source, checked_character_names)
    job.status = "succeeded"
    job.result = {"asset_url": url}
    db.add(job)
    db.commit()
    # ギャラリーへ保存
    try:
        paragraph_ids = payload.get("paragraph_ids")
        meta = {"paragraph_ids": paragraph_ids}
        g = Gallery(
            user_id=user["uid"],
            book_id=book_id,
            asset_url=url,
            type="image",
            prompt=source,
            meta=meta,
        )
        db.add(g)
        db.commit()
        gid = g.id
    except Exception:
        gid = None
    return {"asset_url": url, "gallery_id": gid}


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
    # ギャラリーへ保存
    try:
        paragraph_ids = payload.get("paragraph_ids")
        meta = {"style": style, "aspect": aspect, "paragraph_ids": paragraph_ids}
        gid = None
        if primary:
            g = Gallery(
                user_id=user["uid"],
                book_id=book_id,
                asset_url=primary,
                type="video",
                prompt=source,
                meta=meta,
            )
            db.add(g)
            db.commit()
            gid = g.id
    except Exception:
        gid = None
    return {"asset_url": primary, "video_uris": public, "done": True, "gallery_id": gid}


@router.get("/{job_id}/status")
def job_status(
    job_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    job = db.get(GenerationJob, job_id)
    if not job or job.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job.id, "status": job.status, "result": job.result}
