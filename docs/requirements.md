# 要件定義書

1. プロダクト概要
- 名称（仮）：AI文庫リーダー
- 目的：青空文庫の名著を、現代人にとって「読みやすく」「楽しめる」体験に変換し、読書離れによる教育的損失（集中力・批判的思考・共感力の衰退）をAIによる読書サポートとエンタメ化で克服する。
- 対象ユーザー：
  - 読書習慣が薄い若年層〜社会人
  - 青空文庫を「難しそう」「退屈そう」と感じているが興味はある層
  - 古典に触れたいが途中で挫折しがちな層

2. 提供価値と主機能
- ハードルを下げる：
  - 段落単位の現代語訳（ここだけ訳す）
  - Scholarエージェントによる読書サポート（Q&A）
- 魅力を高める：
  - 挿絵・短尺動画生成とギャラリー保存
- 新しい本との出会い：
  - カテゴリ/ハイブリッド検索とLibrarianによるレコメンド（刺さる一節＋一行理由）

3. ユースケース
- 新たな本の発見
  - 条件で絞り込み（作者/ジャンル/年代）
  - 自然文検索（テーマ・感情・状況など）。Librarianが検索方式（ベクトル/メタ/タイトル/キーワード）を選択
  - レコメンドの「刺さる一節＋一行理由」を読んで興味付け
- 読書サポート
  - 読書ビューでテキスト選択→「ここだけ訳す」→即時に現代語訳
  - 疑問を入力→ScholarがQ&Aで背景・語句説明・要約などを回答
    - テキスト選択→QAの画面に入った場合、選択テキストがそのままQAの入力に入る
    - テキスト選択前は「本書の背景を説明して」「登場人物を解説して」、選択後は「この意味を詳しく解説して」「xxx」など、事前に定めた質問を送信するボタンを表示
  - 選択テキストから挿絵/動画を生成→直後の「。」のあとに挿入して表示
- 補助
  - スクロール位置自動保存→別デバイスでも再開
  - 読了ボタン→完了記録→任意の感想入力ポップアップ→入力後、入力文とハイライトを元に次読む本をレコメンド

4. 機能要件
4.1 検索・発見
- カテゴリ検索
  - 入力：作者/ジャンル/年代（複数指定可）
  - 出力：書籍リスト（タイトル、作者、年代、タグ、サムネ、刺さる一節の有無）
- LLM検索（Librarianの方式選択）
  - 候補方式：
    - ベクトル検索（意味ベース、pgvector）
    - メタ検索（作者/年代/タグのフィルタリング）
    - タイトル検索（厳密一致・部分一致）
    - キーワード検索（BM25相当）
  - Librarianがクエリ意図を解析して方式/重みを決定
  - 出力：関連スコア順の書籍一覧
- レコメンド
  - 入力：ユーザーのハイライト履歴/閲覧履歴/好みベクトル
  - 出力：N件（MVPは5件）の書籍カード
    - 刺さる一節（原文120字以内）
    - 一行理由（40字以内、平易文）
  - 多様性：同作者の連続回避、年代バランス

4.2 読書サポート
- ここだけ訳す（段落現代語訳）
  - 入力：book_id, para_id（または段落テキスト）
  - 出力：
    - translation：現代語訳（最大800字目安）
  - 制約/品質：
    - 固有名詞・地名・人名は原則保持（カナ表記補助のみ）
    - 入力段落は2,000文字以内（超過時は分割）
- 読書サポート（Q&A）
  - 入力：question、book_id、言語=日本語固定
  - 処理：RAG不要、どの作品を読んでいるか、作品名だけプロンプトに持たせる
  - 出力：
    - answer：平易な日本語の回答
  - 制約/品質：
    - 要約/背景説明/語句解説に限定し、創作的ネタバレは明示注記
- 挿絵・挿影（短尺動画）生成
  - 入力：選択文字列 or 段落、スタイルオプション（任意。未指定時は作品調に合うデフォルト）
  - 自動プロンプト整形：
    - 主体（人物/情景/象徴）抽出、不要語除去
    - スタイル候補付与（例：大正浪漫、墨絵、木版画風 等）
  - 画像：Vertex AI Imagen、解像度 1024x1024（MVP）
  - 動画：Vertex AI Veo3、3〜6秒、縦横選択可
  - 出力：asset_url、サムネ、生成メタ（最終プロンプト、モデル、概算コスト）
  - 保存：ユーザーギャラリーへ（再利用・再DL可）
  - 実行方式：非同期ジョブ（queued→running→succeeded/failed、ステータス監視）

4.3 補助機能
- 読書履歴：book_idごとのスクロール位置（相対%）自動保存、再開時に復元
- 読了記録：読了ボタン→completed_at保存→感想入力ポップアップ（任意、500字まで）
- ハイライト：テキスト範囲選択→保存（好みベクトル更新に利用）

5. 非機能要件
- 性能: なし
- 可用性：なし
- セキュリティ
  - 認証：Firebase Auth。匿名ゲストは閲覧のみ、保存系は要ログイン
  - 通信：HTTPS/TLS1.2+
  - データ：最小収集（メール/uid）。PIIは保存時暗号化
  - レート制御：
    - 画像/日10、動画/日2（MVP）
    - Q&A：ユーザー/時 30回（MVP）
- コスト最適化：生成は明示操作時のみ。段落埋め込みは一括前計算。結果キャッシュ（Cloud Storage/短期はアプリメモリ＋Cloud SQL）
- 法的/UX配慮
  - 青空文庫の出典・底本を本文ビューに明記
  - 生成コンテンツには「AIによる解釈例」注記

6. アーキテクチャ
- フロント：HTML + TailwindCSS + Vanilla JS（SPA的遷移最小） フレームワークなし
- バックエンド：FastAPI on Cloud Run（JWT検証、REST API、エージェント呼び出し）
- DB：Cloud SQL (PostgreSQL + pgvector)
- 検索：自前ハイブリッド（ベクトル + タイトル + キーワード + メタ）
- ストレージ：Cloud Storage（本文キャッシュ、生成アセット）
- LLM：Vertex AI（Gemma：軽量訳、Gemini：高度処理/検索オーケストレーション）
- 画像生成：Vertex AI Imagen
- 動画生成：Vertex AI Veo3
- ワークフロー/エージェント連携：Google ADK
- 認証：Firebase Auth
- Serverless VPC Access, Secret Manager

7. マルチエージェント設計（Google ADK）
- Librarian
  - 入力：ユーザークエリ、メタ（履歴/嗜好）
  - 出力：検索方式選択、重み、候補リスト、刺さる一節＋一行理由
- Scholar
  - 入力：段落テキスト or ユーザー質問
  - 出力：現代語訳、難読語注釈（最大2）、Q&A回答と引用
  - ポリシー：固有名詞保持、誤答低減のため前後文脈参照
- Illustrator
  - 入力：テキスト選択/段落、スタイル指示
  - 出力：画像/動画生成ジョブ、ギャラリー登録

8. 画面要件（MVP）
- ホーム/発見
  - 検索バー、カテゴリフィルタ、レコメンドカード（刺さる一節＋一行理由）
- 読書ビュー
  - 本文（段落単位）、選択アクション（訳/挿絵/動画/ハイライト）
  - Q&A入力欄（MVP+）：選択範囲を自動文脈に含めて質問
  - 下部バー：進捗（%）、読了ボタン
  - 出典・底本表示、生成物注記
- ギャラリー
  - サムネ一覧、再利用（再生成/ダウンロード）
- マイページ
  - 履歴（再開）、読了、感想一覧

9. データモデル（例）
- books(id PK, slug, title, author, era, length_chars, tags text[], aozora_source_url, citation, created_at)
- paragraphs(id PK, book_id FK, idx int, text, embed vector(768), char_start int, char_end int)
- highlights(id PK, user_id, book_id, para_id, span_start int, span_end int, text_snippet, created_at)
- tastes(user_id PK, vector vector(256), last_updated)
- gallery(id PK, user_id, book_id, asset_url, thumb_url, type enum(image, video), prompt, meta jsonb, created_at)
- reading_progress(user_id, book_id, scroll_percent numeric(5,2), updated_at, completed_at nullable, PRIMARY KEY(user_id, book_id))
- feedback(id PK, user_id, book_id, text, created_at)
- recommendations_log(id PK, user_id, book_id, quote, one_liner, created_at, clicked bool)
- qa_logs(id PK, user_id, book_id, para_id nullable, question, answer, citations jsonb, latency_ms, created_at)
- インデックス：
  - paragraphs(book_id, idx)、pgvector ivfflat on paragraphs.embed
  - books gin(tags)、trgm(title, author) for タイトル部分一致

10. API（REST, v1）
- 認証：Bearer JWT（GIP）。GET /books 等の閲覧は公開、保存系は要認証
- GET /v1/books?author=&genre=&era=&q=
- GET /v1/books/{book_id}
- GET /v1/books/{book_id}/paragraphs?offset=&limit=
- POST /v1/search/llm { query }
  - レスポンス：items[], method_weights
- GET /v1/recommendations
  - レスポンス：[{book, quote, one_liner}]
- POST /v1/translate { book_id, para_id }
  - レスポンス：{ translation, annotations[], model, latency_ms }
- POST /v1/qa { book_id, para_id?, question }
  - レスポンス：{ answer, citations[], model, latency_ms, confidence }
- POST /v1/highlights { book_id, para_id, span_start, span_end }
- POST /v1/generate/image { book_id, source, style? }
- POST /v1/generate/video { book_id, source, style?, aspect }
- GET /v1/generate/{job_id}/status
- GET /v1/gallery
- POST /v1/progress { book_id, scroll_percent }
- POST /v1/complete { book_id }
- POST /v1/feedback { book_id, text }

11. 業務ロジック/アルゴリズム要件
- 検索ハイブリッド
  - タイトル一致/メタフィルタ/キーワード/BM25(tsvector)/ベクトルが候補
  - Librarianがエージェンティックに検索手法を選択・実行
- レコメンド
  - ユーザーハイライト埋め込み平均→tastes.vector更新
  - 類似度上位から多様性制約（作者/年代）付きでN件抽出
  - 刺さる一節は段落から抽出（max120字）。一行理由は40字以内で平易語彙
- ここだけ訳す
  - 低遅延モデル(Gemma)優先。品質低下時はGeminiへフェイルオーバ（遅延許容時）
  - 難読語抽出：固有名詞除外の頻度/辞書スコアで上位2件
  - キャッシュキー：para_id + モデルバージョン
- Q&A
  - 取得対象：選択段落±N（例：±2）＋作品全体のTop-k（k=5）
  - 回答は引用付きで要点先出し、推測は「推測」と明示
  - ネタバレはユーザー選択時のみ詳細提示（既定は控えめ）
- 生成
  - プロンプト整形：NERで主体抽出、余分な副詞除去、ネガティブプロンプト（現代要素を避ける等）
  - 非同期ジョブ：失敗は最大2回再試行

12. 非機能詳細
- ログ/監査：生成/訳/読了/Q&Aを監査イベントとして保存（PII最小）
- アクセス制御：自ユーザーのみギャラリー/履歴/感想/QAログにアクセス可能
- 国際化：MVPは日本語UI固定
- アクセシビリティ：キーボード操作/コントラスト比 AA 準拠

13. 文献・法的表示要件
- 本文ビューに常時表示：
  - 出典：青空文庫、底本情報、URL
  - 注記：「AIによる解釈例です。正確性は保証されません。」

14. 運用・制限
- 生成回数上限：画像/日10、動画/日10（変更可能）
- Q&Aレート：ユーザー/時 30回（変更可能）
- タイムアウト：画像60秒、動画120秒（バックエンド）。ユーザーには進捗表示
- コンテンツポリシー：不適切生成はブロック（プロンプト/出力の簡易モデレーション）

15. MVPスコープ（実装順）
- 書籍取り込み：短編10〜30本（漱石/芥川/太宰）
- 検索：カテゴリ＋LLMレコメンド
- 読書ビュー：段落選択→ここだけ訳す
- 挿絵生成＋ギャラリー保存
- 履歴保存＋読了ポップアップ
- （MVP+候補）読書サポートQ&A、動画生成
