import argparse
import os
import json
from pathlib import Path
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from google.cloud import storage
import dotenv
from sqlalchemy import text

import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from apps.api.db.session import SessionLocal

dotenv.load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID", "")
LOCATION = os.getenv("LOCATION", "")
BUCKET_NAME = os.getenv("CHARACTERS_BUCKET", "")


def upload_to_gcs(local_path, bucket_name, gcs_path):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_path)
    print(f"Uploaded to gs://{bucket_name}/{gcs_path}")


def generate_image(title, character, appearance):
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    model = ImageGenerationModel.from_pretrained("imagen-4.0-fast-generate-001")
    template = Path(f"preprocessing/07_generate_characters_image.md").read_text(
        encoding="utf-8"
    )
    prompt = template.format(title=title, character=character, appearance=appearance)
    kwargs = {
        "number_of_images": 1,
        "language": "ja",
        "person_generation": "allow_all",
    }
    images = model.generate_images(prompt=prompt, **kwargs)
    filename = f"preprocessing/tmp/{title}/{character}.png"
    images[0].save(location=filename, include_generation_parameters=False)

    # GCSにアップロード
    bucket_name = BUCKET_NAME
    gcs_path = f"{title}/{character}.png"
    upload_to_gcs(filename, bucket_name, gcs_path)


def main():
    db = SessionLocal()
    result = db.execute(text("SELECT title, characters FROM books"))
    characters_json = [(row.title, row.characters) for row in result]
    characters = json.load(
        open(
            "experiment/01_generate_characters_list/characters_list.json",
            "r",
            encoding="utf-8",
        )
    )
    for title, characters in characters_json:
        Path(f"preprocessing/tmp/{title}/").mkdir(parents=True, exist_ok=True)
        for char in characters:
            character = char["name"]
            appearance = "、".join(char["appearance"])
            # filenameのファイルが存在したらcontinue
            filename = f"preprocessing/tmp/{title}/{character.replace('/', '')}.png"
            if Path(filename).exists():
                print(
                    f"Image already exists for {title} - {character} ({appearance}), skipping."
                )
                continue
            print(f"Generating image for {title} - {character} ({appearance})")
            generate_image(title, character, appearance)


if __name__ == "__main__":
    # テスト用プロンプト
    main()
