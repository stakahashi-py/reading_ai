AI文庫リーダー MVP TODO（単一環境 / Firebase Auth）

更新日: 2025-09-05

概要: 要件定義書に準拠して実装・運用タスクを整理。チェックボックスは進捗管理用。

- インフラ（あなた側）
  - [×] Firebase Auth 有効化とサインイン方式設定（Email/Password など）
  - [×] Firebase Web App 作成（apiKey, authDomain, projectId 取得）
  - [×] GCP API 有効化（Cloud Run, Cloud SQL Admin, Cloud Storage, Cloud Tasks, Secret Manager, Vertex AI）
  - [×] Cloud SQL(PostgreSQL15) 作成、`pgvector`/`pg_trgm` 有効化、DB/ユーザー作成
  - [×] GCS バケット作成：`<proj>-aozora-raw`, `<proj>-assets`
  - [×] Cloud Tasks キュー作成：`generation-jobs`（最大再試行2回）
  - [ ] Secret Manager に登録：`DATABASE_URL`, `FIREBASE_PROJECT_ID`, `VERTEX_LOCATION`
  - [×] Cloud Run 用サービスアカウント作成とロール付与（SQL Client, Secret Accessor, Vertex AI User, Storage権限）

- バックエンド API（FastAPI）
  - [ ] OpenAPI スキーマ確認と `/v1/*` I/F 固定
  - [ ] JWT検証（Firebase Admin）環境変数連携（`FIREBASE_PROJECT_ID`）
  - [ ] DB リポジトリ層実装（books/paragraphs/highlights/...）
  - [ ] `/v1/books` 一覧・詳細・段落 取得（実データ接続）
  - [ ] Librarian（ハイブリッド検索：tsvector/BM25相当＋trgm＋メタ＋pgvector 融合）
  - [ ] `/v1/search/llm` 実装（重みと結果返却）
  - [ ] Recommender（taste 更新→多様性制約→刺さる一節＋一行理由）
  - [ ] `/v1/recommendations` 実装
  - [ ] `/v1/translate` Gemma優先＋キャッシュ（キー: para_id+model_version）
  - [ ] `/v1/qa`（MVP+）ストリーミング応答（選択段落±N + Top-k）
  - [ ] `/v1/highlights` 保存＋taste 更新フック
  - [ ] `/v1/progress` 保存、`/v1/complete` 記録（感想は `/v1/feedback`）
  - [ ] 生成API `/v1/generate/image|video`：ジョブ投入、`/v1/generate/{job_id}/status`
  - [ ] 監査ログ（生成/訳/読了/Q&A）保存（PII最小）
  - [ ] レート制限（Q&A/時30、生成/日上限）と簡易モデレーション

- ワーカー（生成/埋め込み）
  - [ ] Cloud Tasks の受信（push handler or pull/専用サービス）
  - [ ] プロンプト整形（NER/不要語除去/ネガティブ）
  - [ ] 画像：Vertex Imagen 呼び出し→GCS 保存→サムネ生成→メタ保存
  - [ ] 動画：Vertex Veo3 呼び出し→GCS 保存→メタ保存
  - [ ] ジョブステータス永続化（queued/running/succeeded/failed, 再試行最大2回）
  - [ ] 段落埋め込み計算（`text-embedding-004`）と再計算ジョブ

- データ取り込み（青空文庫）
  - [ ] インジェストCLI：取得→段落分割→メタ抽出→DB投入
  - [ ] 初期コーパス 10〜30本（漱石/芥川/太宰）
  - [ ] 段落埋め込み投入→索引確認（ivfflat, trgm, gin）

- フロントエンド（MVP）
  - [ ] プロジェクト雛形（HTML, Tailwind, Vanilla JS）
  - [ ] Firebase Auth 連携（ログイン/ログアウト）
  - [ ] 検索/発見 画面（カテゴリ＋LLM検索、レコメンドカード）
  - [ ] 読書ビュー（段落表示・選択アクション：訳/挿絵/動画/ハイライト）
  - [ ] ギャラリー（生成物一覧・再利用/ダウンロード）
  - [ ] マイページ（履歴再開・読了・感想）

- 運用/デプロイ
  - [ ] Dockerfile 作成（api/worker/web）
  - [ ] Cloud Run デプロイ（環境変数/Secret マウント）
  - [ ] DB マイグレーション実行フロー（デプロイ時）
  - [ ] CORS/ドメイン設定、最低限のWAF/Cloud Armor（任意）
  - [ ] 監視ダッシュボード（p95, 生成失敗率, ジョブ滞留）とアラート

- テスト/品質
  - [ ] 単体: Librarian/Recommender/Translator（プロンプト整形含む）
  - [ ] API契約テスト（OpenAPI準拠）
  - [ ] E2E: 検索→読書→訳→挿絵生成の一連
  - [ ] 性能: `/v1/translate` p95 チェック（サンプルデータで）

- ドキュメント
  - [ ] APIエンドポイント一覧とサンプル
  - [ ] インフラ構成図（単一環境）
  - [ ] 運用 Runbook（障害時: SQL接続/ジョブ滞留/Vertex失敗）

- 後回し候補（Backlog）
  - [ ] 動画生成（MVP+）
  - [ ] Q&A ストリーミング（MVP+）
  - [ ] Redis導入（訳キャッシュ/レート制限/ジョブステートの外部化）
  - [ ] Cloud Scheduler（再埋め込み/ログローテ）
  - [ ] Safety出力連携とモデレーション強化

