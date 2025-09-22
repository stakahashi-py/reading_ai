# MAsterpIece

## 概要
- 「名作」をより気軽に、楽しく読んでもらうため、読書を総合的に支援するプロダクトです。
- 詳細はこちら: https://zenn.dev/tea_py/articles/236d753168681e
- このプロダクトは、第3回 AI Agent Hackathon with Google Cloud応募作品です。

## 主なスタック
- FastAPI / SQLAlchemy / Pydantic v2
- Cloud SQL （PostgreSQL 15 + pgvector）
- google-genai（Gemini 2.5 / Imagen / Veo）・Vertex AI・Google Cloud Storage
- Firebase Auth（ローカルでは `AUTH_DISABLED=true` で無効化可）
- Google ADK Agents（外部 Librarian エージェント）
- フロントエンド: `web/` 以下の静的 HTML + TailwindCSS + Vanilla JS

## リポジトリ構成
- `agents/librarian_agent`: Google ADK ベースの司書エージェント。Cloud Run にデプロイして API 経由で呼び出し。
- `apps/api`: FastAPI アプリ本体。`main.py` がエントリーポイント。
- `apps/api/routers/v1`: REST API ルーター群（検索・翻訳・Q&A・生成・進捗・レコメンド・Librarian プロキシなど）。
- `apps/api/services`: LLM 呼び出しや生成ワークフローのサービス層。
- `apps/api/security`: Firebase IDトークンの検証。
- `apps/api/models/models.py`: SQLAlchemy ORM モデル定義。
- `apps/api/db`: DB セッションと接続ユーティリティ。
- `db/schema.sql`: テーブル・拡張・インデックス作成スクリプト。
- `docs/`: Vibe Coding時に参照させたドキュメント。
- `experiment/`: 画像生成まわりの検証スクリプト（キャラクター抽出・キャラ画像生成・シーン画像生成）。
- `preprocessing/`: データ投入・変換・ベクトル化や HTML 生成などのバッチスクリプト群。（詳細は「前処理詳細」を参照）
- `web/`: `search.html` / `read.html` などの静的フロント。`web/books_html/` に段落 HTML を配置。
- `Dockerfile`: Cloud Run向けコンテナ定義。


## 前処理詳細
1. **スキーマ適用** (`01_apply_schema.py`)
   - Cloud SQL Connector を経由してテーブル・拡張を作成する。
2. **青空文庫 HTML 取得（任意）** (`02_get_data.py`)
   - `aozora_html/` に本文 HTML をダウンロードする。
3. **HTML 取り込み・CSV 出力** (`03_ingest_aozora_html.py`)
   - 作品メタと段落データを CSV にエクスポートする。
4. **CSV から DB へ投入** (`04_copy_csv_to_db.py`)
   - 3.で出力した`preprocessing/books.csv` と `preprocessing/paragraphs.csv` を読み込み、DB にコピーする。
5. **ベクトル埋め込み生成** (`05_vectorize.py`)
   - books.summary / paragraphs.text のうち embed が未設定のレコードに Gemini Embedding (`gemini-embedding-001`) を付与する。
6. **キャラクター情報生成** (`06_generate_characters_list.py`)
   - 書籍テーブルに `characters` JSON を追加する。
7. **キャラクター画像生成** (`07_generate_characters_image.py`)
   - キャラクター立ち絵を Vertex Imagen で生成し、`CHARACTERS_BUCKET`（GCS）へ保存する。
8. **段落 HTML のビルド** (`08_build_full_html.py`)
   - `web/books_html/<slug>.html` を生成し、フロントから段落単位で読み込めるようにする。（ローディング高速化のため）
9. **底本情報の追記** (`09_patch_books_html_citation.py`)
   - `aozora_html/` の底本情報を HTML 最終段落に差し込む。
