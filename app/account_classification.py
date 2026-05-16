from __future__ import annotations

import re
from typing import Any

LOW_CONFIDENCE_THRESHOLD = 0.8
NOISY_OCR_KEYS = {"positions"}
GENERIC_ACCOUNT_TITLE_SUFFIXES = (
    "費",
    "料",
    "賃",
    "課",
    "会費",
    "手数料",
    "公課",
    "繰入",
    "損失",
)
TEXT_SIGNAL_EXCLUDED_KEYS = {
    "lid",
    "parent_id",
    "type",
    "date",
    "amount",
    "amount_tax_excluded",
    "purchase_amount",
    "tax",
    "issuer_address",
    "issuer_tel",
    "recipient",
    "registration_number",
    "bank_name",
    "bank_account_type",
    "bank_account_number",
    "bank_account_name",
    "confidences",
    "amount_verification",
    "subtotal_amount_verification",
    "tax_amount_verification",
    "amount_type",
}
ACCOUNT_TITLE_PATTERN = re.compile(r"(?:^|\n)\s*\d{3}\s+([^\s]{2,30})")


def extract_receipt_classification_context(ocr_result: dict[str, Any]) -> dict[str, Any]:
    data = _as_dict(ocr_result.get("data"))
    options = _as_dict(data.get("options"))
    confidences = _as_dict(options.get("confidences"))
    prompt_ocr_result = build_prompt_ocr_result(ocr_result)

    context = {
        "lid": _as_string(ocr_result.get("lid")),
        "parent_id": _as_string(ocr_result.get("parent_id")),
        "type": _as_string(ocr_result.get("type")),
        "date": _as_string(data.get("date")),
        "amount": _as_string(data.get("amount")),
        "amount_tax_excluded": _as_string(data.get("amount_tax_excluded")),
        "purchase_amount": _as_string(data.get("purchase_amount")),
        "tax": _as_string(data.get("tax")),
        "issuer": _as_string(data.get("issuer")),
        "issuer_address": _as_string(data.get("issuer_address")),
        "issuer_tel": _string_list(data.get("issuer_tel")),
        "recipient": _as_string(data.get("recipient")),
        "registration_number": _string_list(options.get("registration_number")),
        "amount_type": _as_string(options.get("amount_type")),
        "confidences": {
            key: value
            for key, value in confidences.items()
            if key
            in {
                "date",
                "amount",
                "amount_tax_excluded",
                "purchase_amount",
                "tax",
                "issuer",
                "issuer_address",
                "issuer_tel",
                "recipient",
            }
        },
        "raw": ocr_result,
        "prompt_ocr_result": prompt_ocr_result,
    }
    context["low_confidence_fields"] = collect_low_confidence_fields(context["confidences"])
    context["review_points"] = build_review_points(context)
    context["text_signals"] = collect_text_signals(prompt_ocr_result)
    context["query"] = build_account_classification_query(context)
    return context


def build_prompt_ocr_result(ocr_result: dict[str, Any]) -> dict[str, Any]:
    prompt_ocr_result = _prune_empty(_strip_noise(ocr_result))
    return prompt_ocr_result if isinstance(prompt_ocr_result, dict) else {}


def build_account_classification_query(context: dict[str, Any]) -> str:
    parts = ["領収書", "勘定科目", "経費分類", "会計処理", "規程"]
    for label, value in (
        ("区分", context.get("type")),
        ("発行者", context.get("issuer")),
        ("発行者住所", context.get("issuer_address")),
        ("日付", context.get("date")),
        ("金額", context.get("amount")),
        ("税額", context.get("tax")),
        ("宛名", context.get("recipient")),
        ("登録番号", ",".join(context.get("registration_number") or [])),
        ("金額種別", context.get("amount_type")),
    ):
        if value:
            parts.append(f"{label}:{value}")
    for text in context.get("text_signals") or []:
        parts.append(f"内容:{text}")
    return " ".join(parts)


def build_review_points(context: dict[str, Any]) -> list[str]:
    review_points: list[str] = []
    if context.get("type") and context.get("type") != "receipt":
        review_points.append("入力種別が receipt ではないため内容確認が必要")
    if not context.get("issuer"):
        review_points.append("発行者名")
    if not context.get("amount"):
        review_points.append("金額")
    if not context.get("date"):
        review_points.append("日付")
    review_points.extend(
        f"OCR信頼度が低い項目: {field}" for field in context.get("low_confidence_fields") or []
    )
    review_points.extend(
        [
            "購入用途",
            "利用者または参加者",
        ]
    )
    return dedupe_strings(review_points)


def collect_low_confidence_fields(confidences: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for key, value in confidences.items():
        scores: list[float] = []
        if isinstance(value, (int, float)):
            scores = [float(value)]
        elif isinstance(value, list):
            scores = [float(item) for item in value if isinstance(item, (int, float))]
        if scores and min(scores) < LOW_CONFIDENCE_THRESHOLD:
            fields.append(key)
    return sorted(set(fields))


def dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        value = _as_string(item)
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def collect_text_signals(value: Any) -> list[str]:
    signals: list[str] = []
    _collect_text_signals(value, signals)
    return dedupe_strings(signals)


def extract_account_title_candidates_from_hits(hits: list[Any]) -> list[str]:
    titles: list[str] = []
    for hit in hits:
        text = _as_string(_get(hit, "text"))
        if not text:
            continue
        for match in ACCOUNT_TITLE_PATTERN.findall(text):
            title = _normalize_candidate_title(match)
            if _looks_like_account_title(title) and _looks_like_expense_title(title):
                titles.append(title)
    return dedupe_strings(titles)


def choose_preferred_account_title(
    account_title: str,
    *,
    candidate_titles: list[str],
) -> str:
    return normalize_to_candidate_title(account_title, candidate_titles)


def build_candidate_alternatives(
    *,
    llm_alternatives: list[str],
    candidate_titles: list[str],
    limit: int = 3,
) -> list[str]:
    alternatives: list[str] = []
    for title in llm_alternatives:
        normalized_title = normalize_to_candidate_title(title, candidate_titles)
        if not normalized_title or normalized_title in alternatives:
            continue
        alternatives.append(normalized_title)
        if len(alternatives) >= limit:
            break
    return alternatives


def normalize_to_candidate_title(account_title: str, candidate_titles: list[str]) -> str:
    if not candidate_titles:
        return ""
    aligned_title = _align_account_title(account_title, candidate_titles)
    return aligned_title if aligned_title in candidate_titles else ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _get(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _as_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in map(str, value) if str(item).strip()]


def _prune_empty(value: Any) -> Any:
    if isinstance(value, dict):
        pruned: dict[str, Any] = {}
        for key, item in value.items():
            normalized = _prune_empty(item)
            if normalized in ("", [], {}, None):
                continue
            pruned[key] = normalized
        return pruned
    if isinstance(value, list):
        pruned_items = [_prune_empty(item) for item in value]
        return [item for item in pruned_items if item not in ("", [], {}, None)]
    if value is None:
        return ""
    return value


def _strip_noise(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        pruned: dict[str, Any] = {}
        for child_key, child_value in value.items():
            if child_key in NOISY_OCR_KEYS:
                continue
            normalized = _strip_noise(child_value, key=child_key)
            if normalized in ("", [], {}, None):
                continue
            pruned[child_key] = normalized
        return pruned
    if isinstance(value, list):
        items = [_strip_noise(item, key=key) for item in value]
        return [item for item in items if item not in ("", [], {}, None)]
    if value is None:
        return ""
    return value


def _collect_text_signals(value: Any, signals: list[str], *, key: str = "") -> None:
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _collect_text_signals(child_value, signals, key=child_key)
        return
    if isinstance(value, list):
        for item in value:
            _collect_text_signals(item, signals, key=key)
        return
    text = _as_string(value)
    if not _is_text_signal(text, key):
        return
    signals.append(text)


def _is_text_signal(text: str, key: str) -> bool:
    if not text or key in TEXT_SIGNAL_EXCLUDED_KEYS:
        return False
    if text.lower() in {"receipt", "unknown", "false", "true"}:
        return False
    if re.fullmatch(r"[0-9T:/.\-]+", text):
        return False
    if re.fullmatch(r"T\d{13}", text):
        return False
    return any(_is_cjk(char) or char.isalpha() for char in text)


def _is_cjk(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x3040 <= codepoint <= 0x30FF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xFF66 <= codepoint <= 0xFF9D
    )


def _normalize_candidate_title(title: str) -> str:
    return title.strip(" /:()[]{}")


def _looks_like_account_title(title: str) -> bool:
    if not title or len(title) < 2 or len(title) > 20:
        return False
    if title in {"コー", "解", "説", "勘定科目名", "科目属性"}:
        return False
    return any(_is_cjk(char) for char in title)


def _looks_like_expense_title(title: str) -> bool:
    if any(title.endswith(suffix) for suffix in GENERIC_ACCOUNT_TITLE_SUFFIXES):
        return True
    return title.startswith("支払") and title.endswith("報酬")


def _align_account_title(account_title: str, candidate_titles: list[str]) -> str:
    if account_title in candidate_titles:
        return account_title
    normalized_account_title = _normalize_account_title(account_title)
    for candidate in candidate_titles:
        normalized_candidate = _normalize_account_title(candidate)
        if normalized_candidate == normalized_account_title:
            return candidate
    for candidate in candidate_titles:
        normalized_candidate = _normalize_account_title(candidate)
        if normalized_candidate.startswith(normalized_account_title) or normalized_account_title.startswith(
            normalized_candidate
        ):
            return candidate
    return account_title


def _normalize_account_title(title: str) -> str:
    normalized = _as_string(title).replace(" ", "")
    if normalized.endswith("費"):
        normalized = normalized[:-1]
    return normalized
