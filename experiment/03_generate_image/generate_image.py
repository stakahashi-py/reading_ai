import argparse
import os
import json
from pathlib import Path
from google import genai
from google.genai import types
import base64
from pydantic import BaseModel
from PIL import Image
from io import BytesIO
import dotenv

dotenv.load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID", "")
# LOCATION = os.getenv("VERTEX_LOCATION", "")
LOCATION = "global"
client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

exp_02_num = "7"  # experiment/02_generate_characters_image/prompts/内、最も良かったプロンプトの番号


class CheckCharactersOutput(BaseModel):
    prompt: str
    character_names: list[str]


def check_characters(title, text, character_names):
    # Geminiを用いて登場人物を抽出
    system = (
        f"「{title}」の一部本文が与えられます。そのシーンを画像化するためのプロンプトと、その中に登場する人物名を、JSON形式で返してください。\n"
        "# 制約条件:\n"
        "- 画像化のためのプロンプトは、英語で出力してください。"
        "- 本文中の要素を、すべてプロンプトに盛り込む必要はありません。印象的なシーンを選び、簡潔に表現してください。\n"
        "- 本文に文脈的な情報が不足する場合でも、本文がどういった場面かを推測してプロンプトに盛り込んでください。\n"
        "- 登場する人物名は、「# 登場人物ホワイトリスト」に記載のある名前のみを候補としてください。それ以外の登場人物がシーンに含まれる場合は、'others'の値を1つだけ、リストに含めてください。\n"
        f"# 本文:\n{text}"
        f"# 登場人物ホワイトリスト:\n{character_names}\n"
    )
    resp = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=system,
        config={
            "response_mime_type": "application/json",
            "response_schema": CheckCharactersOutput,
            "temperature": 0.05,
        },
    )
    resp_json = json.loads(resp.text)
    image_prompt = resp_json.get("prompt")
    checked_character_names = resp_json.get("character_names")
    if "others" in checked_character_names:
        checked_character_names.remove("others")
    print(image_prompt, checked_character_names)
    return image_prompt, checked_character_names


def generate_image(title, content, character_names, exp_num):
    # プロンプトの入れ物準備
    contents = [types.Content(role="user", parts=[])]

    # テキストプロンプトの準備
    prompt_template = Path(
        f"experiment/03_generate_image/prompts/{exp_num}.md"
    ).read_text(encoding="utf-8")
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
        # base64文字列の取得
        path = f"experiment/02_generate_characters_image/pictures/{exp_02_num}/{title}/{character_name}.png"
        with open(path, "rb") as f:
            encoded_str = base64.b64encode(f.read()).decode("utf-8")
        # Partオブジェクト作成
        image_part = types.Part.from_bytes(
            data=base64.b64decode(encoded_str),
            mime_type="image/png",
        )
        # 入れ物に突っ込んでいく
        contents[0].parts.append(image_part)

    # 画像生成実行
    resp = client.models.generate_content(
        model="gemini-2.5-flash-image-preview",
        contents=contents,
        config={"response_modalities": ["TEXT", "IMAGE"]},
    )
    flg = False
    os.makedirs(f"experiment/03_generate_image/pictures/{exp_num}", exist_ok=True)
    for part in resp.candidates[0].content.parts:
        if part.inline_data is not None:
            image = Image.open(BytesIO(part.inline_data.data))
            image.save(
                f"experiment/03_generate_image/pictures/{exp_num}/{title}_{content[:10]}.png"
            )
            flg = True
    if not flg:
        print(f"画像生成に失敗しました。{title}_{content[:10]}")
    return flg


def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--experiment", type=int, help="実験の番号")
    args = argparser.parse_args()
    exp_num = str(args.experiment)

    input_list = json.load(
        open(
            "experiment/03_generate_image/input.json",
            "r",
            encoding="utf-8",
        )
    )
    all_characters = json.load(
        open(
            f"experiment/01_generate_characters_list/characters_list.json",
            "r",
            encoding="utf-8",
        )
    )
    for item in input_list:
        title = item["title"]
        # all_charactersからtitleに対応する登場人物リストを取得
        character_names = []
        for entry in all_characters:
            if entry["title"] == title:
                for character in entry["characters"]:
                    character_names.append(character["name"])
                break
        texts = item["text"]
        for text in texts:
            print(f"タイトル: {title}")
            print(f"本文: {text[:30]}...")
            image_prompt, checked_names = check_characters(title, text, character_names)
            # if not checked_names:
            #     print(f"本文に登場する人物が見つかりません: {title}")
            #     continue
            print(f"抽出された登場人物: {checked_names}")
            retry_count = 0
            while retry_count < 3:
                flg = generate_image(title, image_prompt, checked_names, exp_num)
                if flg:
                    break
                retry_count += 1
                print(f"再試行 {retry_count} 回目")


if __name__ == "__main__":
    main()
