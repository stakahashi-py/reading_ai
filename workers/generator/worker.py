"""
Generator worker stub.
Consumes generation jobs (image/video), calls Vertex, saves to GCS, updates job status.
"""

def handle_job(job: dict) -> dict:
    # TODO: implement Vertex Imagen/Veo calls and storage writes
    return {"status": "succeeded", "asset_url": "gs://bucket/path", "thumb_url": None, "meta": {}}

