# 実装計画（AI文庫リーダー MVP）

最終更新: 2025-09-06

## 前提・スコープ
- 単一環境（Cloud Run + Cloud SQL + Cloud Storage + Cloud Tasks + Vertex AI）。
- 認証は Firebase Auth。閲覧系は公開、保存系は要認証。
- まずは MVP に必要なバックエンド/API と最低限のワーカー/インジェストを優先。

## 現状サマリ（完了）
- インフラ初期設定一式（README/config に準拠）
- DB テーブル定義の作成・適用（`db/schema.sql`, `scripts/apply_schema.py`）
- FastAPI ルータの雛形（`apps/api/routers/v1/*`）

## マイルストーン
1. M1: データ取得と閲覧基盤（books/paragraphs 取得, 認証の骨組み）
2. M2: 検索（Librarian のハイブリッド基盤）
3. M3: レコメンド（taste 更新と多様性制約）
4. M4: 翻訳/QA（Gemma 優先＋キャッシュ、QA は MVP+）
5. M5: 生成とワーカー（画像/動画ジョブ、ステータス永続化）
6. M6: フロント MVP（検索/読書/ギャラリー/マイページ）
7. M7: 運用（デプロイ、監視、レート制限、監査ログ）
8. M8: テスト/ドキュメント（契約/E2E/性能、Runbook/API サンプル）

## 詳細タスク（優先順）

### M1 データ取得・閲覧
- DB リポジトリ層追加: `apps/api/repositories/`
  - `books.py`（一覧/詳細）、`paragraphs.py`（ページング取得）
  - `highlights.py`, `tastes.py`, `gallery.py`, `progress.py`, `feedback.py`
- ルータ実装:
  - `GET /v1/books` フィルタ（author/genre/era/title 部分一致）とページング
  - `GET /v1/books/{id}` 詳細
  - `GET /v1/books/{id}/paragraphs?offset&limit`
- 認証: `apps/api/security/auth.py` で Firebase 検証（既存）を環境変数で制御
- 受け入れ基準: OpenAPI の正常/異常系レスポンス、空データ時の安定動作

### M2 検索（Librarian）
- タイトル/作者 `pg_trgm` による部分一致検索（既存 index 利用）
- キーワード検索（MVP では簡易 `ILIKE` または `tsvector` 導入は後追い）
- ベクトル検索: `paragraphs.embed` 近傍検索（ivfflat）。書籍スコアは段落上位の集約（max/avg）。
- Librarian 戦略:
  - クエリ意図に応じて重み（vector/meta/title/keyword）を決定（MVP は静的 or ルールベース）
  - `/v1/search/llm` は `items[]` と `method_weights` を返却
- 受け入れ基準: 代表的クエリで妥当な上位が返る、重みがレスポンスに含まれる

### M3 レコメンド
- taste 更新: ハイライト登録時に埋め込み平均で `tastes.vector` 更新
- 候補抽出: 類似度上位の書籍から作者/年代多様性制約で N 件選定
- 表示要素: 刺さる一節（120字）＆一行理由（40字）を段落から抽出
- API: `GET /v1/recommendations`（要認証）
- 受け入れ基準: N 件返却、多様性制約が働く、ログ保存（`recommendations_log`）

### M4 翻訳/QA
- `/v1/translate`：Gemma 優先、品質低下時は Gemini へフォールバック（MVP は Gemma のみ）。
- キャッシュ: `para_id + model_version` キー。MVP は DB/JSON キャッシュ or 後日 Redis。
- `/v1/qa`：MVP+。選択段落±N + 作品 Top-k の文脈構成。まずは非ストリーミングで良い。
- ログ: `qa_logs` へ保存（latency, citations）
- 受け入れ基準: p95 レイテンシ確認（サンプルデータ）

### M5 生成とワーカー
- ジョブ永続化テーブル追加: `generation_jobs(id, user_id, type, status, payload, result, created_at, updated_at)`
  - ステータス: queued/running/succeeded/failed、再試行回数
- API:
  - `POST /v1/generate/image|video` → Cloud Tasks キュー投入 → `job_id` 返却
  - `GET /v1/generate/{job_id}/status` → DB 参照
- ワーカー（`workers/generator/worker.py`）
  - プロンプト整形（NER/不要語除去/ネガティブ）
  - Vertex Imagen/Veo 呼び出し → GCS 保存 → サムネ生成 → `gallery` へ保存
  - 失敗は最大2回再試行
- 受け入れ基準: 最低 1 件の画像生成が end-to-end で成功、ステータス遷移が追跡できる

### M6 フロントエンド（MVP）
- 雛形（HTML/Tailwind/Vanilla JS）と Firebase Auth 連携
- 画面: 検索/発見、読書ビュー（訳/挿絵/動画/ハイライト）、ギャラリー、マイページ
- 受け入れ基準: ログイン→検索→書籍閲覧→段落訳→挿絵生成の一連が操作可能

### M7 運用・デプロイ
- Dockerfile（api/worker/web）と Cloud Run デプロイ
- Secret Manager 登録/マウント: `DATABASE_URL`, `FIREBASE_PROJECT_ID`, `VERTEX_LOCATION`
- DB マイグレーション手順（`scripts/apply_schema.py` または Alembic）
- CORS/ドメイン設定、監視（p95, 生成失敗率, キュー滞留）

### M8 テスト/品質
- 単体: Librarian/Recommender/Translator（プロンプト整形を含む）
- 契約: OpenAPI に対する API スモーク
- E2E: 検索→閲覧→訳→挿絵生成
- 性能: `/v1/translate` p95（サンプル）

## 仕様詳細とインターフェイス

### API（確認/補完）
- 既存ルータ: `apps/api/routers/v1/*` に沿って実装。
- 認証:
  - 閲覧（books/paragraphs/search）は公開
  - 保存（highlights/progress/complete/gallery/generate/recommendations/feedback）は要認証
- レート制限（簡易）:
  - 翻訳: 1ユーザー/分 30 リクエスト
  - 生成: 1ユーザー/日 上限（値は設定化）

### データモデルの補足
- 生成ジョブ: `generation_jobs` を追加（M5）。`gallery` は完了時に作成。
- 埋め込み:
  - `paragraphs.embed`: `text-embedding-004`（768 次元）。ivfflat インデックス既存。
  - `tastes.vector`: ハイライトの埋め込み平均で更新。
- 検索用 tsvector は Backlog（必要性が高まれば追加）。

## インジェスト計画（青空文庫）
- CLI（`ingestor/aozora`）を作成:
  - 取得→段落分割（2,000 字以下目安）→メタ抽出（title/author/era/tags）
  - DB 投入後、段落埋め込みをワーカー/バッチで付与
- 初期コーパス: 10〜30 本（漱石/芥川/太宰）
- 検証: ivfflat/trgm/gin インデックス利用の確認

## リスク・設計判断
- ベクトル型の ORM 型付け: MVP は JSON プレースホルダで実装、後日 `sqlalchemy-pgvector` を導入
- BM25/全文検索は Backlog（まずは trgm + vector のハイブリッド）
- QA ストリーミングは MVP+（同期レスから開始）
- キャッシュ/レート制限の本格運用（Redis）は Backlog。MVP は DB ベース/簡易実装。

## 直近 1〜2 スプリント計画（実務）
- S1（今週）
  - Repo 層作成 + `/v1/books/*` を DB 接続で実装
  - Aozora インジェスト CLI（最初の 5 本）と埋め込み投入
  - `/v1/search/llm` の最小ハイブリッド（trgm + vector）
- S2（来週）
  - `/v1/recommendations`（taste 更新 + 多様性）
  - `/v1/translate`（Gemma 接続 + キャッシュ）
  - 生成ジョブ基盤（テーブル追加、Cloud Tasks 経由で画像生成 1 本通す）

## アクションアイテム（未了のインフラ）
- Secret Manager 登録: `DATABASE_URL`, `FIREBASE_PROJECT_ID`, `VERTEX_LOCATION`
- Cloud Run サービスアカウントに必要権限を再確認（SQL/Secrets/Vertex/Storage）

---
補足: 本計画は `docs/requirements.md` および `docs/TODO.md` に整合。実装中に学びがあれば適宜更新すること。

