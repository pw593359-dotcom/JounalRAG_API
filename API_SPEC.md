# Journal RAG API 仕様書

この文書は、現在実装されている `Journal RAG API` の Markdown 仕様書です。  
対象は主に JSON API です。管理画面の HTML ルートは末尾に参考として記載します。

## 1. 基本情報

- API名: `Journal RAG API`
- OpenAPIバージョン: `3.1.0`
- アプリバージョン: `0.1.0`
- ベースURL:
  - ローカル: `http://localhost:8000`
- 認証:
  - なし
- 文字コード:
  - `UTF-8`
- 主なレスポンス形式:
  - `application/json`
- 主なリクエスト形式:
  - `application/json`
  - `multipart/form-data`

## 2. 概要

このAPIは以下を提供します。

- PDF文書のアップロード
- 文書の取り込みジョブ管理
- Elasticsearch ベースのハイブリッド検索
- Gemini を利用した回答生成
- レシートOCR JSONと勘定科目表PDFを使った勘定科目推定
- 管理画面用のHTMLルート

文書アップロード後は非同期で処理されます。  
処理の流れは概ね以下です。

1. PDFをアップロード
2. 文書レコードとジョブレコードを作成
3. Celery worker が PDF テキスト抽出、チャンク分割、埋め込み生成、Elasticsearch 登録を実行
4. 検索APIまたは回答APIで利用

## 3. 共通仕様

### 3.1 エラー応答

バリデーションエラー時は FastAPI 標準の `422` を返します。

例:

```json
{
  "detail": [
    {
      "loc": ["body", "query"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

一部エンドポイントでは業務エラーとして以下も返します。

- `400 Bad Request`
  - 非PDFアップロード
  - `metadata_json` が不正なJSON
- `404 Not Found`
  - 文書またはジョブが存在しない
- `409 Conflict`
  - 再処理対象文書に `source_path` がない
- `503 Service Unavailable`
  - Celeryジョブ投入失敗

### 3.2 日時形式

日時は ISO 8601 形式の文字列です。

例:

```json
"2026-04-11T10:35:50.562569+00:00"
```

### 3.3 文書ステータス

文書 `status` の代表値:

- `queued`
- `processing`
- `ready`
- `failed`

ジョブ `status` の代表値:

- `queued`
- `running`
- `completed`
- `failed`

## 4. データモデル

### 4.1 DocumentOut

```json
{
  "id": "db3d9734-0981-4cfa-a776-8fcbabd511fa",
  "filename": "sample.pdf",
  "content_type": "application/pdf",
  "status": "ready",
  "page_count": 9,
  "chunk_count": 13,
  "metadata": {},
  "text_preview": "先頭本文...",
  "error": null,
  "created_at": "2026-04-11T10:24:38.540805+00:00",
  "updated_at": "2026-04-11T10:35:50.496285+00:00"
}
```

### 4.2 JobOut

```json
{
  "id": "68e46314-58eb-4f35-8b71-243ab11ac521",
  "document_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa",
  "operation": "reindex",
  "status": "completed",
  "stage": "completed",
  "progress": 100,
  "task_id": "777bd269-0046-4490-a2bd-5f95edba747b",
  "error": null,
  "created_at": "2026-04-11T10:35:46.772659+00:00",
  "updated_at": "2026-04-11T10:35:50.562583+00:00",
  "finished_at": "2026-04-11T10:35:50.562569+00:00"
}
```

### 4.3 SearchRequest

```json
{
  "query": "契約更新日は？",
  "top_k": 5,
  "filters": {}
}
```

#### filters の仕様

`filters` は自由形式のオブジェクトですが、現在の実装では以下のように解釈されます。

- `document_id`
  - そのまま `document_id` に一致
- `status`
  - そのまま `status` に一致
- `filename`
  - `filename.keyword` に一致
- `filename.keyword`
  - そのまま一致
- `metadata.xxx`
  - そのまま Elasticsearch の `metadata.xxx` に一致
- 上記以外
  - `metadata.{key}.keyword` に一致

例:

```json
{
  "query": "請求書",
  "top_k": 5,
  "filters": {
    "document_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa",
    "category": "finance"
  }
}
```

この場合、`category` は `metadata.category.keyword` として扱われます。

### 4.4 SearchHit

```json
{
  "chunk_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa:0",
  "document_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa",
  "filename": "sample.pdf",
  "page_number": 1,
  "chunk_index": 0,
  "text": "検索ヒット本文...",
  "score": 1.234,
  "metadata": {}
}
```

### 4.5 AnswerResponse

```json
{
  "query": "契約更新日は？",
  "answer": "契約更新日は2026年4月1日です。[1]",
  "citations": [
    {
      "chunk_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa:0",
      "document_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa",
      "filename": "sample.pdf",
      "page_number": 1,
      "chunk_index": 0,
      "text": "契約更新日は2026年4月1日です。",
      "score": 1.234,
      "metadata": {}
    }
  ]
}
```

### 4.6 AccountClassificationRequest

```json
{
  "ocr_result": {
    "lid": "772_20260319135523.7815_70d5",
    "parent_id": "",
    "type": "receipt",
    "data": {
      "date": "2026-01-13",
      "amount": "5860",
      "tax": "434",
      "issuer": "業務スーパー桃谷店",
      "issuer_address": "大阪市生野区桃谷1-10-22",
      "issuer_tel": ["0667121205"],
      "recipient": "",
      "options": {
        "registration_number": ["T9122001020907"],
        "amount_type": "unknown",
        "confidences": {
          "date": 0.952,
          "amount": 0.97,
          "tax": 0.934,
          "issuer": 0.865
        }
      }
    }
  },
  "top_k": 5,
  "filters": {
    "filename": "勘定科目表.pdf"
  }
}
```

備考:

- `ocr_result` は任意JSONですが、実装上は `type` と `data` 配下の主要項目を使います
- `filters` を省略すると全登録文書が検索対象です
- 複数の勘定科目表PDFがある場合は `document_id` または `filename` で絞る前提です

### 4.7 AccountClassificationResponse

```json
{
  "classification_id": "2a88b2dd-1d9c-4521-a711-0ff2c52c7672",
  "candidates": [
    {
      "account_title": "消耗品費",
      "confidence": 0.7,
      "reason": "業務スーパーでの購入は、事務用品や日常業務で使用する消耗品の購入である可能性が高いです。"
    },
    {
      "account_title": "福利厚生費",
      "confidence": 0.42,
      "reason": "従業員向けの飲食物や備品の購入であれば候補になります。"
    },
    {
      "account_title": "雑費",
      "confidence": 0.2,
      "reason": "用途が不足しており、汎用的な費用科目として残る候補です。"
    }
  ],
  "evidence": ["業務スーパー桃谷店", "5860"],
  "needs_review": true,
  "review_points": ["購入用途", "利用者または参加者"],
  "citations": [
    {
      "chunk_id": "ab19b099-ed2a-4a7a-8bdb-2461a537bc9f:19",
      "document_id": "ab19b099-ed2a-4a7a-8bdb-2461a537bc9f",
      "filename": "勘定科目表.pdf",
      "page_number": 16,
      "chunk_index": 19,
      "text": "737 消耗品費 ...",
      "score": 10.609652,
      "metadata": {}
    }
  ]
}
```

## 5. エンドポイント一覧

| Method | Path | 説明 |
| --- | --- | --- |
| `GET` | `/` | ルート情報 |
| `GET` | `/health` | ヘルスチェック |
| `POST` | `/api/documents` | PDFアップロード |
| `GET` | `/api/documents` | 文書一覧取得 |
| `GET` | `/api/documents/{document_id}` | 文書詳細取得 |
| `DELETE` | `/api/documents/{document_id}` | 文書削除 |
| `POST` | `/api/documents/{document_id}/reindex` | 文書再処理 |
| `GET` | `/api/jobs` | ジョブ一覧取得 |
| `GET` | `/api/jobs/{job_id}` | ジョブ詳細取得 |
| `POST` | `/api/search` | 検索 |
| `POST` | `/api/answer` | 回答生成 |
| `POST` | `/api/account-classifications` | レシートOCR JSONから勘定科目推定 |

## 6. 詳細仕様

### 6.1 `GET /`

APIの基本情報を返します。

#### Response `200 OK`

```json
{
  "name": "Journal RAG API",
  "admin": "/admin/documents",
  "docs": "/docs"
}
```

### 6.2 `GET /health`

API、Elasticsearch、Redis の接続状態を返します。

#### Response `200 OK`

```json
{
  "status": "ok",
  "elasticsearch": true,
  "redis": true,
  "environment": "development"
}
```

`status` は、Elasticsearch と Redis の両方が正常なら `ok`、そうでなければ `degraded` です。

### 6.3 `POST /api/documents`

PDFファイルをアップロードし、非同期取り込みジョブを作成します。

#### Request

- Content-Type: `multipart/form-data`

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `file` | file | yes | PDFファイル |
| `metadata_json` | string | no | JSON文字列。オブジェクト形式のみ許可 |

#### 例

```bash
curl -X POST http://localhost:8000/api/documents \
  -F "file=@sample.pdf" \
  -F 'metadata_json={"source":"manual","category":"finance"}'
```

#### Response `202 Accepted`

```json
{
  "document": {
    "id": "db3d9734-0981-4cfa-a776-8fcbabd511fa",
    "filename": "sample.pdf",
    "content_type": "application/pdf",
    "status": "queued",
    "page_count": null,
    "chunk_count": 0,
    "metadata": {
      "source": "manual",
      "category": "finance"
    },
    "text_preview": null,
    "error": null,
    "created_at": "2026-04-11T10:24:38.540805+00:00",
    "updated_at": "2026-04-11T10:24:38.540805+00:00"
  },
  "job": {
    "id": "dd9b1345-75e5-4ee7-a59a-d69d768fe0b8",
    "document_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa",
    "operation": "ingest",
    "status": "queued",
    "stage": "queued",
    "progress": 0,
    "task_id": "9bb5e516-c546-44ae-b533-890dda1633e4",
    "error": null,
    "created_at": "2026-04-11T10:24:38.796855+00:00",
    "updated_at": "2026-04-11T10:24:38.796855+00:00",
    "finished_at": null
  },
  "task_id": "9bb5e516-c546-44ae-b533-890dda1633e4"
}
```

#### 業務エラー

- `400 Bad Request`
  - アップロードファイルがPDFではない
  - `metadata_json` が不正なJSON
  - `metadata_json` がJSONオブジェクトではない
- `503 Service Unavailable`
  - Celery キュー投入失敗

### 6.4 `GET /api/documents`

文書一覧を返します。新しいものが先です。

#### Response `200 OK`

```json
[
  {
    "id": "db3d9734-0981-4cfa-a776-8fcbabd511fa",
    "filename": "sample.pdf",
    "content_type": "application/pdf",
    "status": "ready",
    "page_count": 9,
    "chunk_count": 13,
    "metadata": {},
    "text_preview": "先頭本文...",
    "error": null,
    "created_at": "2026-04-11T10:24:38.540805+00:00",
    "updated_at": "2026-04-11T10:35:50.496285+00:00"
  }
]
```

### 6.5 `GET /api/documents/{document_id}`

指定文書の詳細を返します。

#### Path Parameters

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `document_id` | string | yes | 文書ID |

#### Response `200 OK`

`DocumentOut`

#### 業務エラー

- `404 Not Found`
  - 文書が存在しない

### 6.6 `DELETE /api/documents/{document_id}`

文書、関連チャンク、関連ジョブ、アップロードファイルを削除します。

#### Path Parameters

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `document_id` | string | yes | 文書ID |

#### Response `204 No Content`

レスポンスボディはありません。

備考:
- 対象が存在しない場合でも、実装上は削除処理がそのまま走るため、削除系としては冪等に近い挙動です。

### 6.7 `POST /api/documents/{document_id}/reindex`

既存文書を再抽出・再埋め込み・再インデックスします。

#### Path Parameters

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `document_id` | string | yes | 文書ID |

#### Response `200 OK`

`JobOut`

#### 例

```bash
curl -X POST \
  http://localhost:8000/api/documents/db3d9734-0981-4cfa-a776-8fcbabd511fa/reindex
```

#### 業務エラー

- `404 Not Found`
  - 文書が存在しない
- `409 Conflict`
  - 文書に `source_path` がない
- `503 Service Unavailable`
  - Celery キュー投入失敗

### 6.8 `GET /api/jobs`

ジョブ一覧を返します。新しいものが先です。

#### Response `200 OK`

```json
[
  {
    "id": "68e46314-58eb-4f35-8b71-243ab11ac521",
    "document_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa",
    "operation": "reindex",
    "status": "completed",
    "stage": "completed",
    "progress": 100,
    "task_id": "777bd269-0046-4490-a2bd-5f95edba747b",
    "error": null,
    "created_at": "2026-04-11T10:35:46.772659+00:00",
    "updated_at": "2026-04-11T10:35:50.562583+00:00",
    "finished_at": "2026-04-11T10:35:50.562569+00:00"
  }
]
```

### 6.9 `GET /api/jobs/{job_id}`

指定ジョブの詳細を返します。

#### Path Parameters

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `job_id` | string | yes | ジョブID |

#### Response `200 OK`

`JobOut`

#### 業務エラー

- `404 Not Found`
  - ジョブが存在しない

### 6.10 `POST /api/search`

Gemini の埋め込みモデルでクエリをベクトル化し、Elasticsearch でハイブリッド検索を実行します。

#### Request

- Content-Type: `application/json`

```json
{
  "query": "契約更新日は？",
  "top_k": 5,
  "filters": {}
}
```

#### Response `200 OK`

```json
{
  "query": "契約更新日は？",
  "hits": [
    {
      "chunk_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa:0",
      "document_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa",
      "filename": "sample.pdf",
      "page_number": 1,
      "chunk_index": 0,
      "text": "契約更新日は2026年4月1日です。",
      "score": 1.234,
      "metadata": {}
    }
  ]
}
```

#### 備考

- `query` は必須
- `top_k` は `1` から `50`
- `hits` が空配列になることがあります

### 6.11 `POST /api/answer`

検索APIで取得したチャンクを根拠として、Gemini に回答文を生成させます。

#### Request

```json
{
  "query": "契約更新日は？",
  "top_k": 5,
  "filters": {}
}
```

#### Response `200 OK`

```json
{
  "query": "契約更新日は？",
  "answer": "契約更新日は2026年4月1日です。[1]",
  "citations": [
    {
      "chunk_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa:0",
      "document_id": "db3d9734-0981-4cfa-a776-8fcbabd511fa",
      "filename": "sample.pdf",
      "page_number": 1,
      "chunk_index": 0,
      "text": "契約更新日は2026年4月1日です。",
      "score": 1.234,
      "metadata": {}
    }
  ]
}
```

#### 根拠ゼロ件時の挙動

検索でヒットが1件もない場合は以下を返します。

```json
{
  "query": "契約更新日は？",
  "answer": "文書内に根拠が見つかりませんでした。",
  "citations": []
}
```

### 6.12 `POST /api/account-classifications`

レシートOCR JSONを受け取り、勘定科目表PDFなどの登録文書をRAG検索した上で、該当しそうな勘定科目候補を信頼度順に最大3件返します。

#### Request

- Content-Type: `application/json`

```json
{
  "ocr_result": {
    "lid": "772_20260319135523.7815_70d5",
    "parent_id": "",
    "type": "receipt",
    "data": {
      "date": "2026-01-13",
      "amount": "5860",
      "tax": "434",
      "issuer": "業務スーパー桃谷店",
      "issuer_address": "大阪市生野区桃谷1-10-22",
      "issuer_tel": ["0667121205"],
      "recipient": "",
      "options": {
        "registration_number": ["T9122001020907"],
        "amount_type": "unknown",
        "confidences": {
          "date": 0.952,
          "amount": 0.97,
          "tax": 0.934,
          "issuer": 0.865
        }
      }
    }
  },
  "top_k": 5,
  "filters": {
    "filename": "勘定科目表.pdf"
  }
}
```

#### Response `200 OK`

```json
{
  "classification_id": "2a88b2dd-1d9c-4521-a711-0ff2c52c7672",
  "candidates": [
    {
      "account_title": "消耗品費",
      "confidence": 0.7,
      "reason": "業務スーパーでの購入は、事務用品や日常業務で使用する消耗品の購入である可能性が高いです。"
    },
    {
      "account_title": "福利厚生費",
      "confidence": 0.42,
      "reason": "従業員向けの飲食物や備品の購入であれば候補になります。"
    },
    {
      "account_title": "会議費",
      "confidence": 0.18,
      "reason": "会議用の飲食物や備品購入であれば候補になります。"
    }
  ],
  "evidence": ["業務スーパー桃谷店", "5860"],
  "needs_review": true,
  "review_points": [
    "OCR信頼度が低い項目: issuer_address",
    "購入用途",
    "利用者または参加者"
  ],
  "citations": [
    {
      "chunk_id": "ab19b099-ed2a-4a7a-8bdb-2461a537bc9f:19",
      "document_id": "ab19b099-ed2a-4a7a-8bdb-2461a537bc9f",
      "filename": "勘定科目表.pdf",
      "page_number": 16,
      "chunk_index": 19,
      "text": "737 消耗品費 ...",
      "score": 10.609652,
      "metadata": {}
    }
  ]
}
```

#### 備考

- `candidates` は信頼度降順で、最大3件です
- `needs_review` は、人手確認が必要な場合に `true` になります
- OCRの信頼度が低い項目がある場合や、用途・参加者が不足している場合は `needs_review=true` に寄ります
- `citations` には根拠として使ったチャンクを返します
- 参照PDFを固定したい場合は `filters.document_id` または `filters.filename` を付けてください

## 7. 管理画面ルート

以下は API というより HTML 管理画面です。

| Method | Path | 説明 |
| --- | --- | --- |
| `GET` | `/admin` | 管理画面トップ。`/admin/documents` へリダイレクト |
| `GET` | `/admin/documents` | 文書一覧画面 |
| `POST` | `/admin/documents` | 画面からPDFアップロード |
| `GET` | `/admin/documents/{document_id}` | 文書詳細画面 |
| `POST` | `/admin/documents/{document_id}/delete` | 画面から文書削除 |
| `POST` | `/admin/documents/{document_id}/reindex` | 画面から再処理 |
| `GET` | `/admin/jobs` | ジョブ一覧画面 |
| `GET` | `/admin/api-spec` | Markdown仕様書のHTML表示 |
| `GET` | `/admin/search` | 検索テスト画面 |
| `POST` | `/admin/search` | 画面から検索または回答生成 |

主な画面URL:

- `http://localhost:8000/admin/documents`
- `http://localhost:8000/admin/jobs`
- `http://localhost:8000/admin/api-spec`
- `http://localhost:8000/admin/search`

## 8. OpenAPI 参照

実行中のAPIから自動生成される定義も利用できます。

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## 9. 未実装項目

以下は現時点では本仕様書の対象外です。

- 認証/認可
- APIキー
- レート制限
- 監査ログ
- OCR
- PDF以外の文書取り込み
