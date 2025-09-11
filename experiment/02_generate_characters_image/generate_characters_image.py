import argparse
import os
import json
from pathlib import Path
import vertexai  # type: ignore
from vertexai.preview.vision_models import ImageGenerationModel  # type: ignore

import dotenv

dotenv.load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID", "")
LOCATION = os.getenv("LOCATION", "")


def generate_image(title, character, appearance, experiment_num):
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    model = ImageGenerationModel.from_pretrained("imagen-4.0-fast-generate-001")
    template = Path(
        f"experiment/02_generate_characters_image/prompts/{experiment_num}.md"
    ).read_text(encoding="utf-8")
    prompt = template.format(title=title, character=character, appearance=appearance)
    kwargs = {
        "number_of_images": 1,
        "language": "ja",
        "person_generation": "allow_all",
    }
    images = model.generate_images(prompt=prompt, **kwargs)
    filename = f"experiment/02_generate_characters_image/pictures/{experiment_num}/{title}/{character}.png"
    images[0].save(location=filename, include_generation_parameters=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment_num", type=int, help="プロンプトテンプレート番号")
    parser.add_argument(
        "--one_title",
        type=bool,
        default=False,
        help="テスト用に1タイトルのみ生成するかどうか",
    )
    args = parser.parse_args()

    experiment_num = str(args.experiment_num)
    one_title = args.one_title

    characters = json.load(
        open(
            "experiment/01_generate_characters_list/characters_list.json",
            "r",
            encoding="utf-8",
        )
    )
    for item in characters:
        title = item["title"]
        Path(
            f"experiment/02_generate_characters_image/pictures/{experiment_num}/{title}"
        ).mkdir(parents=True, exist_ok=True)
        for char in item["characters"]:
            character = char["name"]
            appearance = "、".join(char["appearance"])
            print(f"Generating image for {title} - {character} ({appearance})")
            generate_image(title, character, appearance, experiment_num)
        if one_title:
            break


if __name__ == "__main__":
    # テスト用プロンプト
    main()
