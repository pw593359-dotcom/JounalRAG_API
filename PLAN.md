# FastAPI + Elasticsearch + Gemini RAG API 設計計画

## Summary

- 新規プロジェクトとして、Docker Compose で `api`、`celery_worker`、`redis`、`elasticsearch` を起動する構成にする。
- FastAPI は管理画面と内部向け JSON API を提供し、文書登録、PDF取り込み、チャンク化、Gemini 埋め込み生成、Elasticsearch ハイブリッド検索、Gemini 回答生成まで担当する。
- 認証は初期版では入れない。メタデータ、文書、チャンク、ジョブ状態は PostgreSQL 等を使わず Elasticsearch のみで管理する。

## Key Changes

- 技術スタックは `FastAPI`、`Jinja2 + HTMX`、`Celery + Redis`、`Elasticsearch`、`google-genai`、`pypdf`、`pytest` とする。
- Elasticsearch は `rag_documents`、`rag_chunks`、`rag_jobs` の3インデックスを作る。`rag_chunks` は本文、文書ID、ページ番号、チャンク番号、メタデータ、`dense_vector` 768次元、作成日時を持つ。
- Gemini は安定版優先で、埋め込みは `gemini-embedding-001`、`output_dimensionality=768`、回答生成は `gemini-2.5-flash` をデフォルトにし、どちらも環境変数で上書き可能にする。768次元・1536次元・3072次元は公式に推奨範囲として確認済み。
- PDF は `pypdf` でテキスト抽出する。スキャンPDFなど抽出不能なものは OCR せず、ジョブを `failed` にして理由を保存する。
- チャンク化は再帰的文字分割で、初期値は `chunk_size=1000` 文字、`chunk_overlap=150` 文字。日本語PDFでも扱いやすいよう、段落、改行、句点、空白の順で分割する。
- 検索はハイブリッド検索にする。質問文を Gemini でベクトル化し、Elasticsearch の kNN 検索と BM25 全文検索を組み合わせ、上位チャンクを引用情報付きで返す。
- 回答生成 API は検索結果チャンクだけをコンテキストに入れ、回答本文、引用チャンク、スコア、参照文書情報を JSON で返す。根拠が不足する場合は「文書内に根拠が見つからない」扱いにする。

## Public Interfaces

### 管理画面

- `GET /admin/documents`: 文書一覧、PDFアップロード、削除、再処理
- `GET /admin/documents/{document_id}`: 文書詳細、抽出テキスト、チャンク、ジョブ履歴
- `GET /admin/search`: 検索と回答生成の手動テスト
- `GET /admin/jobs`: 取り込み・再処理ジョブ状態

### JSON API

- `POST /api/documents`: PDFアップロード、取り込みジョブ作成
- `GET /api/documents`: 文書一覧取得
- `GET /api/documents/{id}`: 文書詳細取得
- `DELETE /api/documents/{id}`: 文書削除
- `POST /api/documents/{id}/reindex`: 再抽出・再埋め込み
- `GET /api/jobs/{id}`: ジョブ状態確認
- `POST /api/search`: `query`, `top_k`, `filters` を受け取り、引用チャンクを返す
- `POST /api/answer`: `query`, `top_k`, `filters` を受け取り、Gemini 生成回答と引用を返す
- `GET /health`: API、Redis、Elasticsearch の接続状態を返す

## Test Plan

- ユニットテスト: PDFテキスト抽出、チャンク分割、Geminiクライアントのモック、ESドキュメント変換、検索レスポンス整形。
- 統合テスト: Docker Compose 上で ES インデックス作成、PDF投入ジョブ、チャンク保存、ハイブリッド検索、回答生成のモック動作を検証。
- 管理画面テスト: アップロード、一覧表示、ジョブ状態表示、検索テスト画面の基本導線を確認。
- 失敗系: Gemini APIキー未設定、PDF抽出失敗、ES接続失敗、ジョブ再試行失敗、検索結果ゼロ件を検証。

## Assumptions

- 作業ディレクトリは空で Git リポジトリではないため、新規プロジェクトとして設計する。
- 初期版は開発用で認証なし。外部公開する段階で管理者ログイン、APIキー、レート制限、監査ログを追加する。
- OCR、Webページ取り込み、マルチテナント、Kubernetes、本番監視は初期スコープ外。
- 参考にした一次情報:
  - Elasticsearch dense vector/kNN: <https://www.elastic.co/docs/solutions/search/vector/dense-vector>
  - Gemini Embeddings: <https://ai.google.dev/gemini-api/docs/embeddings>
  - Gemini Models: <https://ai.google.dev/gemini-api/docs/models>
