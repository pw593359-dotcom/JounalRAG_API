from __future__ import annotations

from typing import TYPE_CHECKING

from .account_classification import (
    build_candidate_alternatives,
    choose_preferred_account_title,
    dedupe_strings,
    extract_account_title_candidates_from_hits,
    extract_receipt_classification_context,
    normalize_to_candidate_title,
)
from .prompting import build_account_classification_prompt, build_answer_prompt
from .schemas import (
    AccountClassificationAlternative,
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
        "account_title": {"type": "string"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "alternatives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "account_title": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["account_title", "reason"],
            },
        },
        "needs_review": {"type": "boolean"},
        "review_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "account_title",
        "confidence",
        "reason",
        "evidence",
        "alternatives",
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
        account_title = _text_or_default(payload.get("account_title"), "要確認")
        account_title = choose_preferred_account_title(
            account_title,
            candidate_titles=candidate_titles,
        )
        additional_review_points: list[str] = []
        if candidate_titles and not account_title:
            additional_review_points.append("参照文書の勘定科目候補に一致する名称を選べませんでした。")
            account_title = "要確認"
        elif not candidate_titles:
            additional_review_points.append("参照文書から勘定科目候補を抽出できませんでした。")
            account_title = "要確認"

        confidence = _coerce_confidence(payload.get("confidence"))
        reason = _text_or_default(payload.get("reason"), "根拠が不足しているため確認が必要です。")
        evidence = _string_list(payload.get("evidence"))
        if not citations and not evidence:
            evidence = ["勘定科目規程の検索結果は見つかりませんでした。"]

        llm_alternative_titles = []
        alternative_reason_map: dict[str, str] = {}
        for item in payload.get("alternatives", []) if isinstance(payload.get("alternatives"), list) else []:
            if not isinstance(item, dict):
                continue
            raw_title = _text_or_default(item.get("account_title"), "")
            if not raw_title:
                continue
            llm_alternative_titles.append(raw_title)
            alternative_reason_map[raw_title] = _text_or_default(item.get("reason"), "")

        alternatives = []
        for candidate_title in build_candidate_alternatives(
            llm_alternatives=llm_alternative_titles,
            candidate_titles=candidate_titles,
            limit=3,
        ):
            mapped_reason = ""
            for raw_title in llm_alternative_titles:
                if normalize_to_candidate_title(raw_title, candidate_titles) == candidate_title:
                    mapped_reason = alternative_reason_map.get(raw_title, "")
                    break
            alternatives.append(
                AccountClassificationAlternative(
                    account_title=candidate_title,
                    reason=mapped_reason or "参照文書から抽出した勘定科目候補です。",
                )
            )

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
        if account_title == "要確認":
            needs_review = True

        return AccountClassificationResponse(
            account_title=account_title,
            confidence=confidence,
            reason=reason,
            evidence=evidence,
            alternatives=alternatives,
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
            account_title="要確認",
            confidence=0.0,
            reason="勘定科目の推論結果を生成できなかったため、手動確認が必要です。",
            evidence=["API側でJSON形式の分類結果を生成できませんでした。"],
            alternatives=[],
            needs_review=True,
            review_points=review_points,
            citations=citations,
        )


def _coerce_confidence(value) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _merge_review_points(base: list[str], extra: list[str]) -> list[str]:
    return dedupe_strings([*base, *extra])


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _text_or_default(value, default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or default
