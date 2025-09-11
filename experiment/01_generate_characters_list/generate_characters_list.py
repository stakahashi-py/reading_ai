import json
import os
from google import genai
from pydantic import BaseModel
import dotenv

dotenv.load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID", "")
LOCATION = os.getenv("VERTEX_LOCATION", "")
LLM_MODEL = "gemini-2.5-flash"

client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


# 構造化出力用のPydanticモデル
class Character(BaseModel):
    name: str
    appearance: list[str]


class Characters(BaseModel):
    characters: list[Character]


def generate_characters_list(title, author):
    # プロンプト作成
    system = (
        "与えられた『作品タイトル』と『著者名』から、主要な登場人物の名前と、見た目の特徴をJSONで返してください。\n"
        "# 注記\n"
        "- 見た目の特徴は、後続の画像生成に利用します。画像生成に適した特徴を列挙してください。\n"
        "- 「主要キャラクター」とは、作品内に複数回登場するキャラクターを指します。1場面にしか出てこないキャラクター以外は、全て出力してください。\n"
        "- 1キャラクターごとに、nameとappearanceを1スキーマ、出力してください。複数キャラクターを1スキーマまで出力することはできません。\n"
        "- 場面ごとに外見(髪型・顔などの通常変化し得ない要素)や年齢が大きく変化する場合、「name」を別の名前にして、複数回出力してください。\n"
        "- 画像生成の際、当該キャラクター1人のみが出力されるようなappearanceを出力してください。他の人物の情報が含まれないようにしてください。\n"
        # "- 解答の際は必要に応じてWeb検索を行い、情報を補完してください。\n"
    )
    example = [
        {
            "name": "李徴（人間）",
            "appearance": [
                "唐代の若い文人風（20代後半〜30代前半）",
                "痩せ型・蒼白ぎみの肌",
                "切れ長の目・神経質な表情",
                "長めの黒髪を高い髷にまとめる（唐代の束髪）",
                "濃紺〜墨色の唐代学者の深衣（長衣）",
                "幞頭（黒い布帽）を着用",
            ],
        },
        {
            "name": "李徴（虎）",
            "appearance": [
                "大型のベンガルトラ風の体格（やや痩せぎみ）",
                "黄褐色の体毛に黒い縞模様",
                "知性を感じる憂いを帯びた眼差し",
                "長く鋭い犬歯と白い髭",
                "耳は立ち気味で神経質に動く",
                "前脚の先に土埃・岩場の傷跡",
            ],
        },
        {
            "name": "袁傪",
            "appearance": [
                "唐代の中堅官吏（30代後半〜40代）",
                "落ち着いた体躯・端正な姿勢",
                "短い整えられた口髭・顎髭",
                "深い瑠璃色または黒の官服（広袖）",
                "幞頭（黒の官帽）",
                "腰帯に笏（または玉佩）を下げる",
                "冷静で思いやりのある眼差し",
                "旅装（外套・薄いマント）",
            ],
        },
    ]
    system_prompt = f"{system}\n\n例 タイトル=山月記 作者=中島敦:\n{json.dumps(example, ensure_ascii=False)}\n\n"
    user_prompt = f"タイトル: {title}\n著者名: {author}"

    # 生成
    grounding_tool = genai.types.Tool(google_search=genai.types.GoogleSearch())
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_prompt,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "response_schema": Characters,
            "tools": [grounding_tool],
            "temperature": 0.05,
        },
    )
    return resp.text


def main():
    all_response = []
    title_author_list = [
        ("山月記", "中島敦"),
        ("羅生門", "芥川龍之介"),
        ("注文の多い料理店", "宮沢賢治"),
        ("銀河鉄道の夜", "宮沢賢治"),
        ("走れメロス", "太宰治"),
        ("人間失格", "太宰治"),
        ("こころ", "夏目漱石"),
        ("坊っちゃん", "夏目漱石"),
        ("吾輩は猫である", "夏目漱石"),
        ("舞姫", "森鴎外"),
    ]
    for title, author in title_author_list:
        print(f"タイトル: {title}, 著者: {author}")
        retry_count = 0
        while retry_count < 5:
            try:
                characters = generate_characters_list(title, author)
                print(characters)
                characters = json.loads(characters)["characters"]
                all_response.append({"title": title, "characters": characters})
                break
            except Exception as e:
                print(f"Error: {e}")
                retry_count += 1
                continue
    with open(
        "experiment/01_generate_characters_list/characters_list.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(all_response, f, ensure_ascii=False, indent=2)
    print("キャラクターリストを characters_list.json に保存しました。")


if __name__ == "__main__":
    main()
