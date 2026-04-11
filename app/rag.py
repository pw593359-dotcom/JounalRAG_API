from __future__ import annotations

from typing import TYPE_CHECKING

from .prompting import build_answer_prompt
from .schemas import AnswerResponse, SearchHit, SearchResponse

if TYPE_CHECKING:
    from .elastic import ElasticRagStore
    from .gemini import GeminiService


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
