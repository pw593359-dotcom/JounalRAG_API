from __future__ import annotations

from typing import TYPE_CHECKING

from .account_classification import (
    dedupe_strings,
    extract_account_title_candidates_from_hits,
    extract_receipt_classification_context,
    normalize_ranked_candidates,
)
from .prompting import build_account_classification_prompt, build_answer_prompt
from .schemas import (
    AccountClassificationCandidate,
    AccountClassificationResponse,
    AnswerResponse,
    SearchHit,
    SearchResponse,
)

if TYPE_CHECKING:
    from .elastic import ElasticRagStore
    from .gemini import GeminiService


ACCOUNT_CLASSIFICATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "account_title": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["account_title", "confidence", "reason"],
            },
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
        "needs_review": {"type": "boolean"},
        "review_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "candidates",
        "evidence",
        "needs_review",
        "review_points",
    ],
}


class RagService:
    def __init__(self, store: ElasticRagStore, gemini: GeminiService) -> None:
        self.store = store
        self.gemini = gemini

    def search(
        self,
        *,
        query: str,
        top_k: int,
        filters: dict | None = None,
    ) -> SearchResponse:
        vector = self.gemini.embed_text(query)
        hits = self.store.hybrid_search(
            query_text=query,
            vector=vector,
            top_k=top_k,
            filters=filters or {},
        )
        return SearchResponse(
            query=query,
            hits=[SearchHit(**hit) for hit in hits],
        )

    def answer(
        self,
        *,
        query: str,
        top_k: int,
        filters: dict | None = None,
    ) -> AnswerResponse:
        search_response = self.search(query=query, top_k=top_k, filters=filters)
        if not search_response.hits:
            return AnswerResponse(
                query=query,
                answer="文書内に根拠が見つかりませんでした。",
                citations=[],
            )

        prompt = build_answer_prompt(query, search_response.hits)
        answer_text = self.gemini.generate_answer(prompt)
        return AnswerResponse(
            query=query,
            answer=answer_text,
            citations=search_response.hits,
        )

    def classify_account(
        self,
        *,
        ocr_result: dict,
        top_k: int,
        filters: dict | None = None,
    ) -> AccountClassificationResponse:
        normalized_filters = filters or {}
        receipt_context = extract_receipt_classification_context(ocr_result)
        search_response = self.search(
            query=receipt_context["query"],
            top_k=top_k,
            filters=normalized_filters,
        )
        candidate_titles = extract_account_title_candidates_from_hits(search_response.hits)
        prompt = build_account_classification_prompt(
            receipt_context,
            search_response.hits,
            candidate_titles=candidate_titles,
        )
        try:
            payload = self.gemini.generate_json(
                prompt,
                response_schema=ACCOUNT_CLASSIFICATION_RESPONSE_SCHEMA,
            )
        except Exception as exc:
            response = self._classification_fallback(
                receipt_context=receipt_context,
                citations=search_response.hits,
                error_message=str(exc),
            )
        else:
            response = self._classification_response(
                payload=payload,
                receipt_context=receipt_context,
                citations=search_response.hits,
            )

        record = self.store.create_account_classification(
            ocr_result=ocr_result,
            top_k=top_k,
            filters=normalized_filters,
            response=response.model_dump(),
        )
        return response.model_copy(update={"classification_id": record["id"]})

    def _classification_response(
        self,
        *,
        payload: dict,
        receipt_context: dict,
        citations: list[SearchHit],
    ) -> AccountClassificationResponse:
        candidate_titles = extract_account_title_candidates_from_hits(citations)
        additional_review_points: list[str] = []
        if not candidate_titles:
            additional_review_points.append("参照文書から勘定科目候補を抽出できませんでした。")

        evidence = _string_list(payload.get("evidence"))
        if not citations and not evidence:
            evidence = ["勘定科目規程の検索結果は見つかりませんでした。"]

        candidates = [
            AccountClassificationCandidate(**item)
            for item in normalize_ranked_candidates(
                payload.get("candidates"),
                candidate_titles,
                limit=3,
            )
        ]
        if candidate_titles and not candidates:
            additional_review_points.append("参照文書の勘定科目候補に一致する名称を選べませんでした。")
        if not candidates:
            candidates = [
                AccountClassificationCandidate(
                    account_title="要確認",
                    confidence=0.0,
                    reason="参照文書の勘定科目候補に一致する名称を選べないため確認が必要です。",
                )
            ]

        review_points = _merge_review_points(
            receipt_context.get("review_points") or [],
            [
                *_string_list(payload.get("review_points")),
                *additional_review_points,
            ],
        )
        if not citations:
            review_points = _merge_review_points(
                review_points,
                ["勘定科目規程の検索結果が見つかりませんでした。"],
            )

        needs_review = bool(payload.get("needs_review", False))
        if receipt_context.get("type") != "receipt":
            needs_review = True
        if receipt_context.get("low_confidence_fields"):
            needs_review = True
        if not citations:
            needs_review = True
        if candidates[0].account_title == "要確認":
            needs_review = True

        return AccountClassificationResponse(
            candidates=candidates,
            evidence=evidence,
            needs_review=needs_review,
            review_points=review_points,
            citations=citations,
        )

    def _classification_fallback(
        self,
        *,
        receipt_context: dict,
        citations: list[SearchHit],
        error_message: str,
    ) -> AccountClassificationResponse:
        review_points = _merge_review_points(
            receipt_context.get("review_points") or [],
            [f"分類結果の生成に失敗: {error_message}"],
        )
        if not citations:
            review_points = _merge_review_points(
                review_points,
                ["勘定科目規程の検索結果が見つかりませんでした。"],
            )
        return AccountClassificationResponse(
            candidates=[
                AccountClassificationCandidate(
                    account_title="要確認",
                    confidence=0.0,
                    reason="勘定科目の推論結果を生成できなかったため、手動確認が必要です。",
                )
            ],
            evidence=["API側でJSON形式の分類結果を生成できませんでした。"],
            needs_review=True,
            review_points=review_points,
            citations=citations,
        )


def _merge_review_points(base: list[str], extra: list[str]) -> list[str]:
    return dedupe_strings([*base, *extra])


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
