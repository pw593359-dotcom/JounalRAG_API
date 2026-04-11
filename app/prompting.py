from collections.abc import Sequence
from typing import Any


def build_answer_prompt(query: str, hits: Sequence[Any]) -> str:
    context_blocks = []
    for index, hit in enumerate(hits, start=1):
        document_id = _get(hit, "document_id", "")
        filename = _get(hit, "filename") or document_id
        page_number = _get(hit, "page_number") or "-"
        chunk_id = _get(hit, "chunk_id", "")
        text = _get(hit, "text", "")
        location = f"{filename} p.{page_number}"
        context_blocks.append(
            f"[{index}] {location}\n"
            f"chunk_id: {chunk_id}\n"
            f"{text}"
        )

    context = "\n\n".join(context_blocks)
    return (
        "あなたは社内文書検索のRAGアシスタントです。\n"
        "以下のコンテキストだけを根拠に、日本語で簡潔に回答してください。\n"
        "根拠が不足する場合は、文書内に根拠が見つからないと答えてください。\n"
        "回答末尾に参照番号を [1] の形式で含めてください。\n\n"
        f"質問:\n{query}\n\n"
        f"コンテキスト:\n{context}\n"
    )


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)

