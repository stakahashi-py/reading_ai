AI 文庫リーダー（MVP）

本リポジトリは、青空文庫テキストを読みやすくするためのミニマルな「検索・閲覧・翻訳・Q&A・挿絵/動画生成」アプリのMVPです。バックエンドは FastAPI、DB は PostgreSQL（pgvector/pg_trgm）を利用します。静的フロントは `web/` 直下にあり、API から配信されます。

主なスタック
- FastAPI（Python）/ SQLAlchemy
- PostgreSQL + 拡張: `vector`, `pg_trgm`
- Google Gemini（google-genai; Vertex AI または API Key）
- Firebase Auth（ローカル開発では無効化可）

リポジトリ構成
- `apps/api`: FastAPI 本体（`/v1/*` ルーター）
- `apps/api/security/auth.py`: Firebase 認証（ローカルでは `AUTH_DISABLED=true` で無効化）
- `apps/api/models/models.py`: ORM モデル
- `db/schema.sql`: テーブル・拡張・インデックス作成スクリプト
- `preprocessing/`: 事前処理スクリプト群（スキーマ適用/取得/取り込み/ベクトル化）
- `web/`: 検索画面（`search.html`）と読書画面（`read.html`）
- `docs/requirements.md`: 要件定義・仕様メモ

必要環境
- Python 3.10 以上
- PostgreSQL 14 以上（拡張: `vector`, `pg_trgm`）
- Google Cloud（任意）: Vertex AI / Cloud SQL / Cloud Storage（生成物保存用）

環境変数（抜粋）
- DB 接続（いずれか）
  - `CONNECTION_NAME`, `DB_USER`, `DB_NAME`, `DB_PASS`（Cloud SQL Connector）
  - もしくは `DATABASE_URL`（例: `postgresql+psycopg://user:pass@host:5432/db`）
- モデル関連: `PROJECT_ID`, `VERTEX_LOCATION`（例: `asia-northeast1` または `us-central1`）, 代替として `GOOGLE_API_KEY`
- 認証: `FIREBASE_PROJECT_ID`, `AUTH_DISABLED=true`（ローカル開発向け）
- 生成出力: `ASSETS_BUCKET`, `ASSETS_URL_PREFIX`（任意）, `VEO_MODEL_ID`

セットアップ（ローカル）
1) 依存関係のインストール
- `python -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`

2) 環境変数の設定
- `.env.example` を参考に `.env` を作成し、上記の値を設定してください。

重要: 実行前の前処理
- 本アプリを起動する前に、`preprocessing` 配下のスクリプトを「上から順に」実行してください（番号順）。
- 代表的な実行手順は以下です。

1. スキーマ適用（拡張作成含む）
   - Cloud SQL を使う場合: `python preprocessing/01_apply_schema.py`
   - あるいは手動: お使いの DB で `db/schema.sql` を実行

2. 青空文庫データの取得（任意・必要に応じて）
   - `python preprocessing/02_get_data.py`
   - `aozora_html/` に本文 HTML が保存されます（既に用意済みなら不要）。

3. 本文 HTML の取り込み（CSV 作成）
   - 例: `python preprocessing/03_ingest_aozora_html.py --out-dir preprocessing --limit 50`
   - メタ生成に Gemini を使用（`PROJECT_ID` もしくは `GOOGLE_API_KEY` が必要。`--no-llm` で無効化可）。
   - 注意: `04_copy_csv_to_db.py` が参照するのは `preprocessing/books.csv` と `preprocessing/paragraphs.csv` です。上記のように `--out-dir preprocessing` を指定してください（未指定だと `preprocessing/out_csv/` に出力されます）。

4. CSV を DB へ投入
   - `python preprocessing/04_copy_csv_to_db.py`
   - Cloud SQL Connector（`CONNECTION_NAME`, `DB_USER`, `DB_NAME`, `DB_PASS`）を利用します。

5. 段落ベクトルの作成（pgvector への保存）
   - `python preprocessing/05_vectorize_paragraph.py`
   - Embedding: `text-embedding-004`（google-genai）。`PROJECT_ID`+`VERTEX_LOCATION` または `GOOGLE_API_KEY` が必要です。

アプリの起動
- `uvicorn apps.api.main:app --reload`
- ヘルスチェック: `http://localhost:8000/healthz`
- 画面
  - 検索: `http://localhost:8000/web/search.html`
  - 読む: `http://localhost:8000/web/read.html?book_id=<ID>`

認証について
- 既定では Firebase トークン検証を行います。ローカル開発では `.env` に `AUTH_DISABLED=true` を設定すると認証をバイパスできます。

主な API（/v1）
- `GET /v1/books`, `GET /v1/books/{book_id}`, `GET /v1/books/{book_id}/paragraphs`
- `POST /v1/search/title`（タイトル専用の高速検索）/ `POST /v1/search/llm`（ハイブリッド）
- `POST /v1/translate`（段落の現代語訳）
- `POST /v1/qa` / `POST /v1/qa/stream`（Q&A）
- `POST /v1/highlights` / `GET /v1/highlights`
- `POST /v1/generate/image` / `POST /v1/generate/video` / `GET /v1/generate/{job_id}/status`
- `POST /v1/progress` / `GET /v1/progress` / `POST /v1/complete`
- `POST /v1/feedback` / `GET /v1/feedback` / `PUT /v1/feedback/{id}`

トラブルシューティング
- DB 接続に失敗する: `CONNECTION_NAME/DB_USER/DB_NAME/DB_PASS` または `DATABASE_URL` を確認。
- `vector`/`pg_trgm` が無い: `CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;` を実行。
- 検索結果が空: 事前処理（特に CSV 投入とベクトル化）を実行済みか確認。

ライセンス/出典
- 青空文庫のテキストは各作品の配布条件に従ってご利用ください。本アプリは教育・検証目的のMVPです。

リンク
- 仕様: `docs/requirements.md`
- スキーマ: `db/schema.sql`
