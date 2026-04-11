# Journal RAG API

FastAPI、Elasticsearch、Gemini、Celery、Redis を使ったPDF向けRAG APIです。管理画面からPDFを登録し、ワーカーでテキスト抽出、チャンク化、Gemini埋め込み生成、Elasticsearchへの登録を行います。検索APIと回答生成APIも同じアプリで提供します。

## 構成

- `api`: FastAPI、JSON API、管理画面
- `worker`: Celery worker、PDF抽出、埋め込み生成、ESインデックス
- `elasticsearch`: 文書、チャンク、ジョブ状態、ベクトル検索
- `redis`: Celery broker/result backend

## 起動

```bash
cp .env.example .env
```

`.env` の `RAG_GEMINI_API_KEY` に Gemini API キーを設定します。

```bash
docker compose up --build
```

起動後に使う主なURLです。

- 管理画面: `http://localhost:8000/admin/documents`
- OpenAPI: `http://localhost:8000/docs`
- ヘルスチェック: `http://localhost:8000/health`
- Elasticsearch: `http://localhost:9200`

## API

```bash
curl -X POST http://localhost:8000/api/documents \
  -F "file=@sample.pdf" \
  -F 'metadata_json={"source":"manual"}'
```

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"契約更新日は？","top_k":5,"filters":{}}'
```

```bash
curl -X POST http://localhost:8000/api/answer \
  -H "Content-Type: application/json" \
  -d '{"query":"契約更新日は？","top_k":5,"filters":{}}'
```

## 設定

主な環境変数です。

- `RAG_GEMINI_API_KEY`: Gemini API キー
- `RAG_GEMINI_EMBEDDING_MODEL`: 既定値 `gemini-embedding-001`
- `RAG_GEMINI_GENERATION_MODEL`: 既定値 `gemini-2.5-flash`
- `RAG_EMBEDDING_DIMENSIONS`: 既定値 `768`
- `RAG_CHUNK_SIZE`: 既定値 `1000`
- `RAG_CHUNK_OVERLAP`: 既定値 `150`
- `RAG_ELASTICSEARCH_URL`: 既定値 `http://localhost:9200`
- `RAG_REDIS_URL`: 既定値 `redis://localhost:6379/0`

## テスト

```bash
python3 -m unittest discover -s tests
```

依存関係を入れた環境では次も使えます。

```bash
pytest
```

## 初期版の制限

- PDFのみ対応します。
- スキャンPDFのOCRは行いません。
- 認証、APIキー、レート制限、監査ログは未実装です。
- メタデータ、文書、チャンク、ジョブ状態は Elasticsearch のみに保存します。

