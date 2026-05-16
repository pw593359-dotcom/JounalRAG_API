from collections.abc import Sequence
import json
from typing import Any


def build_answer_prompt(query: str, hits: Sequence[Any]) -> str:
    context = "\n\n".join(_build_context_blocks(hits))
    return (
        "あなたは社内文書検索のRAGアシスタントです。\n"
        "以下のコンテキストだけを根拠に、日本語で簡潔に回答してください。\n"
        "根拠が不足する場合は、文書内に根拠が見つからないと答えてください。\n"
        "回答末尾に参照番号を [1] の形式で含めてください。\n\n"
        f"質問:\n{query}\n\n"
        f"コンテキスト:\n{context}\n"
    )


def build_account_classification_prompt(
    receipt_context: dict[str, Any],
    hits: Sequence[Any],
    *,
    candidate_titles: Sequence[str] | None = None,
) -> str:
    summary = {
        "lid": receipt_context.get("lid"),
        "type": receipt_context.get("type"),
        "issuer": receipt_context.get("issuer"),
        "issuer_address": receipt_context.get("issuer_address"),
        "issuer_tel": receipt_context.get("issuer_tel"),
        "recipient": receipt_context.get("recipient"),
        "date": receipt_context.get("date"),
        "amount": receipt_context.get("amount"),
        "tax": receipt_context.get("tax"),
        "registration_number": receipt_context.get("registration_number"),
        "amount_type": receipt_context.get("amount_type"),
        "text_signals": receipt_context.get("text_signals"),
        "low_confidence_fields": receipt_context.get("low_confidence_fields"),
        "review_points": receipt_context.get("review_points"),
    }
    prompt_ocr_result = receipt_context.get("prompt_ocr_result") or receipt_context.get("raw") or {}
    context = "\n\n".join(_build_context_blocks(hits)) or "（参照コンテキストなし）"
    account_title_candidates = list(candidate_titles or [])
    candidate_titles_block = (
        json.dumps(account_title_candidates, ensure_ascii=False, indent=2)
        if account_title_candidates
        else "[]"
    )
    return (
        "あなたは日本の経費精算における勘定科目分類アシスタントです。\n"
        "必ずJSONオブジェクトのみを返してください。Markdownやコードフェンスは禁止です。\n"
        "参照コンテキストに含まれる勘定科目、解説、仕訳例、運用ルールを最優先で使ってください。\n"
        "参照コンテキストから抽出した勘定科目候補が空でなければ、candidates の account_title はその候補一覧から選んでください。\n"
        "参照コンテキストから抽出した勘定科目候補に正式名称があれば、その表記をそのまま使ってください。\n"
        "一般名に言い換えず、候補一覧にある正式名称を返してください。\n"
        "OCR JSONに存在しない用途、参加者、社内事情を断定しないでください。\n"
        "上位3件までの候補を confidence の高い順で candidates に入れてください。候補が3件未満なら存在する件数だけ返してください。\n"
        "参照コンテキストが弱い場合や候補一覧に適切な科目が見当たらない場合は candidates の先頭を 要確認 とし、needs_review を true にしてください。\n"
        "各 candidate の account_title は単一の勘定科目名、confidence は 0 から 1 の数値、reason は日本語1-3文で返してください。\n"
        "evidence は短い日本語文字列の配列、review_points は確認すべき点の配列にしてください。\n"
        "返却JSONのキー:\n"
        "{\n"
        '  "candidates": [{"account_title": string, "confidence": number, "reason": string}],\n'
        '  "evidence": string[],\n'
        '  "needs_review": boolean,\n'
        '  "review_points": string[]\n'
        "}\n\n"
        f"領収書の要約:\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n\n"
        "領収書OCR JSON（分類に不要な座標情報などは除外済み）:\n"
        f"{json.dumps(prompt_ocr_result, ensure_ascii=False, indent=2)}\n\n"
        "参照コンテキストから抽出した勘定科目候補:\n"
        f"{candidate_titles_block}\n\n"
        f"参照コンテキスト:\n{context}\n"
    )


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _build_context_blocks(hits: Sequence[Any]) -> list[str]:
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
    return context_blocks
