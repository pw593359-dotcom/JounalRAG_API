# 領収書OCR JSONから勘定科目を推定するAPI追加

## Summary

- `POST /api/account-classifications` を新設し、AI-OCR済みの領収書JSONから推奨勘定科目を返す。
- 勘定科目マスタは別途持たず、既存Elasticsearch上の規程・科目説明文書をRAG検索し、その根拠を最優先する。
- RAG根拠が弱い場合でもLLM推定は返すが、`needs_review=true` と追加確認点を付けて監査しやすくする。

## Key Changes

- 新しいリクエスト/レスポンススキーマを追加する。
  - Request: `ocr_result: dict`, `top_k: int = 5`, `filters: dict = {}`。
  - `ocr_result` は top-level に `lid`, `parent_id`, `type`, `data` を持つAI-OCR結果を想定する。
  - `type` は初期版では `receipt` のみ分類対象とし、それ以外は `needs_review=true` で返す。
  - Response: `account_title`, `confidence`, `reason`, `evidence`, `alternatives`, `needs_review`, `review_points`, `citations`。
- `RagService` に領収書分類用メソッドを追加する。
  - `ocr_result.data` の `issuer`, `amount`, `tax`, `date`, `recipient`, `issuer_address`, `issuer_tel`, `options.registration_number`, `options.amount_type` など、存在するキーから検索クエリを組み立てる。
  - `data.options.confidences` が低い項目はプロンプト内で「OCR信頼度が低い情報」として扱い、分類の断定度を下げる。
  - `data.options.positions` は座標情報のため、初期版では分類判断には使わない。ただしデバッグ用にLLMへ渡す元JSONには残す。
  - 既存の `hybrid_search` で規程文書を取得し、取得チャンクをGeminiの分類プロンプトへ渡す。
- `prompting.py` に分類専用プロンプトを追加する。
  - 「コンテキストを最優先」「入力JSONにない事実を補わない」「必ず候補科目1つを返す」「根拠が弱い場合は `needs_review=true`」を明記する。
  - 勘定科目はRAG文書内の表現を優先し、見つからない場合のみ一般的な推定として `会議費`、`交際費`、`旅費交通費`、`消耗品費`、`福利厚生費`、`新聞図書費`、`雑費` などから選ぶ。
  - 例: `issuer` がスーパー、食料品店、飲食店等の場合でも、社内規程の根拠・用途情報が不足する場合は `needs_review=true` を優先する。
- `GeminiService` にJSON生成メソッドを追加する。
  - `GenerateContentConfig(response_mime_type="application/json")` を使い、LLM出力をJSONとしてパースする。
  - パース失敗時は分類APIを500にせず、`needs_review=true` のフォールバックレスポンスを返す。
- 管理画面は初期版では追加しない。OpenAPI `/docs` から試せるAPIのみ提供する。

## API Contract

`POST /api/account-classifications`

```json
{
  "ocr_result": {
    "lid": "772_20260319135523.7815_70d5",
    "parent_id": "",
    "type": "receipt",
    "data": {
      "date": "2026-01-13",
      "amount": "5860",
      "amount_tax_excluded": "",
      "purchase_amount": "",
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
  "filters": {}
}
```

Response例:

```json
{
  "account_title": "消耗品費",
  "confidence": 0.52,
  "reason": "発行者が業務スーパーであり、領収書JSONには購入用途や参加者情報が含まれていないため、規程文書の根拠を優先しつつ一般的には消耗品費候補と推定する。ただし食料品の用途によって会議費・福利厚生費・交際費等に変わる可能性がある。",
  "evidence": ["検索された規程文書で、物品購入や食料品の扱いに関する記述があればその要約を入れる"],
  "alternatives": [
    {
      "account_title": "会議費",
      "reason": "会議用の飲食物購入であれば候補になる"
    },
    {
      "account_title": "交際費",
      "reason": "取引先接待や贈答目的であれば候補になる"
    }
  ],
  "needs_review": true,
  "review_points": ["購入用途", "購入明細", "参加者または利用対象", "社内規程上の食料品購入の扱い"],
  "citations": []
}
```

## Test Plan

- ユニットテスト:
  - 提供されたAI-OCR JSON形状から `data.issuer`, `data.amount`, `data.tax`, `data.date`, `data.options.registration_number`, `data.options.confidences` を抽出できること。
  - OCR JSONからRAG検索クエリを作る処理。
  - `type != "receipt"` の場合に `needs_review=true` 相当の分類へ寄せること。
  - 分類プロンプトが領収書JSON、RAGチャンク、JSON出力制約を含むこと。
  - Gemini JSON生成の正常系、JSONパース失敗時のフォールバック。
- APIテスト:
  - `POST /api/account-classifications` が固定JSON構造を返すこと。
  - RAG検索結果ありの場合に `citations` が返ること。
  - RAG検索結果なしの場合も `needs_review=true` でLLM推定を返すこと。
- 既存テスト:
  - `pytest` と `python3 -m unittest discover -s tests` を通す。
  - `/api/search`、`/api/answer` の既存挙動は変更しない。

## Assumptions

- AI-OCRの入力JSONは、提供された `lid` / `parent_id` / `type` / `data` 形式を標準形として扱う。
- `data.options.positions` はOCR座標情報として保持するが、初期版の分類ロジックでは重視しない。
- 未知のキーも分類プロンプトへ含める。
- 経費規程・科目説明などの根拠文書は、既存のPDF取り込み機能でElasticsearchに登録済み、または登録される前提。
- 科目候補の専用マスタ、管理画面、仕訳作成、税区分判定は今回の初期スコープ外。
- 勘定科目の最終判断は会計・社内規程に依存するため、根拠が弱いケースは `needs_review=true` で人間確認に回す。
