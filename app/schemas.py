from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    id: str = Field(description="文書ID")
    filename: str = Field(description="元のファイル名")
    content_type: str | None = Field(default=None, description="MIMEタイプ")
    status: str = Field(description="文書処理状態。queued / processing / ready / failed")
    page_count: int | None = Field(default=None, description="PDFのページ数")
    chunk_count: int | None = Field(default=None, description="登録済みチャンク数")
    metadata: dict[str, Any] = Field(default_factory=dict, description="任意メタデータ")
    text_preview: str | None = Field(default=None, description="抽出テキストの先頭プレビュー")
    error: str | None = Field(default=None, description="失敗時のエラーメッセージ")
    created_at: datetime | str = Field(description="作成日時")
    updated_at: datetime | str = Field(description="更新日時")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "ab19b099-ed2a-4a7a-8bdb-2461a537bc9f",
                "filename": "勘定科目表.pdf",
                "content_type": "application/pdf",
                "status": "ready",
                "page_count": 19,
                "chunk_count": 24,
                "metadata": {},
                "text_preview": "ACCOUNTING REFERENCE...",
                "error": None,
                "created_at": "2026-05-16T10:00:00+00:00",
                "updated_at": "2026-05-16T10:01:00+00:00",
            }
        }
    )


class JobOut(BaseModel):
    id: str = Field(description="ジョブID")
    document_id: str = Field(description="対象文書ID")
    operation: str = Field(description="ジョブ種別。ingest / reindex")
    status: str = Field(description="ジョブ状態。queued / running / completed / failed")
    stage: str | None = Field(default=None, description="ジョブの詳細ステージ")
    progress: int = Field(default=0, description="進捗率")
    task_id: str | None = Field(default=None, description="CeleryタスクID")
    error: str | None = Field(default=None, description="失敗時のエラーメッセージ")
    created_at: datetime | str = Field(description="作成日時")
    updated_at: datetime | str = Field(description="更新日時")
    finished_at: datetime | str | None = Field(default=None, description="完了日時")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "68e46314-58eb-4f35-8b71-243ab11ac521",
                "document_id": "ab19b099-ed2a-4a7a-8bdb-2461a537bc9f",
                "operation": "reindex",
                "status": "completed",
                "stage": "completed",
                "progress": 100,
                "task_id": "777bd269-0046-4490-a2bd-5f95edba747b",
                "error": None,
                "created_at": "2026-05-16T10:05:00+00:00",
                "updated_at": "2026-05-16T10:05:05+00:00",
                "finished_at": "2026-05-16T10:05:05+00:00",
            }
        }
    )


class DocumentCreateResponse(BaseModel):
    document: DocumentOut = Field(description="作成された文書")
    job: JobOut = Field(description="起票された取り込みジョブ")
    task_id: str | None = Field(default=None, description="CeleryタスクID")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document": DocumentOut.model_config["json_schema_extra"]["example"],
                "job": {
                    "id": "dd9b1345-75e5-4ee7-a59a-d69d768fe0b8",
                    "document_id": "ab19b099-ed2a-4a7a-8bdb-2461a537bc9f",
                    "operation": "ingest",
                    "status": "queued",
                    "stage": "queued",
                    "progress": 0,
                    "task_id": "9bb5e516-c546-44ae-b533-890dda1633e4",
                    "error": None,
                    "created_at": "2026-05-16T10:00:00+00:00",
                    "updated_at": "2026-05-16T10:00:00+00:00",
                    "finished_at": None,
                },
                "task_id": "9bb5e516-c546-44ae-b533-890dda1633e4",
            }
        }
    )


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, description="検索クエリ")
    top_k: int = Field(default=5, ge=1, le=50, description="取得件数")
    filters: dict[str, Any] = Field(default_factory=dict, description="検索対象を絞るフィルタ")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "勘定科目表の消耗品費は？",
                "top_k": 5,
                "filters": {"filename": "勘定科目表.pdf"},
            }
        }
    )


class SearchHit(BaseModel):
    chunk_id: str = Field(description="チャンクID")
    document_id: str = Field(description="文書ID")
    filename: str | None = Field(default=None, description="ファイル名")
    page_number: int | None = Field(default=None, description="ページ番号")
    chunk_index: int = Field(description="文書内チャンク番号")
    text: str = Field(description="ヒット本文")
    score: float = Field(description="検索スコア")
    metadata: dict[str, Any] = Field(default_factory=dict, description="チャンクメタデータ")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "chunk_id": "ab19b099-ed2a-4a7a-8bdb-2461a537bc9f:19",
                "document_id": "ab19b099-ed2a-4a7a-8bdb-2461a537bc9f",
                "filename": "勘定科目表.pdf",
                "page_number": 16,
                "chunk_index": 19,
                "text": "737 消耗品費 消耗品費 文房具・コピー用紙・プリンターインク...",
                "score": 12.25,
                "metadata": {},
            }
        }
    )


class SearchResponse(BaseModel):
    query: str = Field(description="検索クエリ")
    hits: list[SearchHit] = Field(description="ヒット一覧")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "勘定科目表の消耗品費は？",
                "hits": [SearchHit.model_config["json_schema_extra"]["example"]],
            }
        }
    )


class AnswerRequest(SearchRequest):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "消耗品費の説明を教えて",
                "top_k": 5,
                "filters": {"filename": "勘定科目表.pdf"},
            }
        }
    )


class AnswerResponse(BaseModel):
    query: str = Field(description="質問文")
    answer: str = Field(description="生成された回答")
    citations: list[SearchHit] = Field(description="回答根拠として使ったチャンク")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "消耗品費の説明を教えて",
                "answer": "消耗品費は、文房具やコピー用紙など短期間で消費される物品に使う科目です。[1]",
                "citations": [SearchHit.model_config["json_schema_extra"]["example"]],
            }
        }
    )


class AccountClassificationRequest(BaseModel):
    ocr_result: dict[str, Any] = Field(description="レシートOCR結果JSON")
    top_k: int = Field(default=5, ge=1, le=50, description="検索に使う上位チャンク件数")
    filters: dict[str, Any] = Field(default_factory=dict, description="参照文書を絞るフィルタ")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
                                "amount_tax_excluded": 0,
                                "purchase_amount": 0,
                                "tax": 0.934,
                                "issuer": 0.865,
                                "issuer_address": 0,
                                "issuer_tel": [0.932],
                                "recipient": 0,
                            },
                        },
                    },
                },
                "top_k": 5,
                "filters": {"filename": "勘定科目表.pdf"},
            }
        }
    )


class AccountClassificationCandidate(BaseModel):
    account_title: str = Field(description="候補の勘定科目名")
    confidence: float = Field(ge=0.0, le=1.0, description="候補の推定信頼度")
    reason: str = Field(description="その候補になる理由")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "account_title": "雑費",
                "confidence": 0.42,
                "reason": "購入内容が不明なため、少額で汎用的な費用科目として残る候補です。",
            }
        }
    )


class AccountClassificationResponse(BaseModel):
    classification_id: str | None = Field(default=None, description="分類結果の保存ID")
    candidates: list[AccountClassificationCandidate] = Field(
        default_factory=list,
        description="信頼度順に並んだ勘定科目候補。最大3件",
    )
    evidence: list[str] = Field(default_factory=list, description="推定時に使った主要手掛かり")
    needs_review: bool = Field(default=False, description="人手確認が必要かどうか")
    review_points: list[str] = Field(default_factory=list, description="確認すべきポイント")
    citations: list[SearchHit] = Field(default_factory=list, description="参照した文書チャンク")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "classification_id": "2a88b2dd-1d9c-4521-a711-0ff2c52c7672",
                "candidates": [
                    {
                        "account_title": "消耗品費",
                        "confidence": 0.8,
                        "reason": "業務スーパーでの購入は、事業活動に必要な消耗品の購入である可能性が高いです。",
                    },
                    {
                        "account_title": "福利厚生費",
                        "confidence": 0.42,
                        "reason": "従業員向けの飲食物や備品の購入であれば候補になります。",
                    },
                    AccountClassificationCandidate.model_config["json_schema_extra"]["example"],
                ],
                "evidence": ["業務スーパー桃谷店", "5860"],
                "needs_review": True,
                "review_points": [
                    "OCR信頼度が低い項目: amount_tax_excluded",
                    "OCR信頼度が低い項目: issuer_address",
                    "購入用途",
                    "利用者または参加者",
                ],
                "citations": [SearchHit.model_config["json_schema_extra"]["example"]],
            }
        }
    )


class AccountClassificationStoredOut(BaseModel):
    classification_id: str = Field(description="分類結果ID")
    created_at: datetime | str = Field(description="作成日時")
    updated_at: datetime | str = Field(description="更新日時")
    top_k: int = Field(description="検索時に使った top_k")
    filters: dict[str, Any] = Field(default_factory=dict, description="適用したフィルタ")
    ocr_result: dict[str, Any] = Field(description="元のOCR結果JSON")
    result: AccountClassificationResponse = Field(description="保存された分類結果")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "classification_id": "2a88b2dd-1d9c-4521-a711-0ff2c52c7672",
                "created_at": "2026-05-16T10:15:00+00:00",
                "updated_at": "2026-05-16T10:15:00+00:00",
                "top_k": 5,
                "filters": {"filename": "勘定科目表.pdf"},
                "ocr_result": AccountClassificationRequest.model_config["json_schema_extra"]["example"]["ocr_result"],
                "result": AccountClassificationResponse.model_config["json_schema_extra"]["example"],
            }
        }
    )
