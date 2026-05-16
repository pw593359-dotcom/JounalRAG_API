import unittest
from types import SimpleNamespace

from app.account_classification import (
    build_account_classification_query,
    build_candidate_alternatives,
    collect_low_confidence_fields,
    extract_account_title_candidates_from_hits,
    extract_receipt_classification_context,
    normalize_to_candidate_title,
)
from app.prompting import build_account_classification_prompt


SAMPLE_OCR_RESULT = {
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
                "issuer": 0.865,
            },
            "positions": {"issuer": {"left_top": {"x": 1, "y": 2}}},
        },
    },
}


class AccountClassificationTests(unittest.TestCase):
    def test_collect_low_confidence_fields_handles_scalars_and_lists(self):
        result = collect_low_confidence_fields(
            {
                "issuer": 0.7,
                "amount": 0.95,
                "issuer_tel": [0.92, 0.75],
            }
        )

        self.assertEqual(result, ["issuer", "issuer_tel"])

    def test_extract_receipt_context_preserves_expected_fields(self):
        context = extract_receipt_classification_context(SAMPLE_OCR_RESULT)

        self.assertEqual(context["type"], "receipt")
        self.assertEqual(context["issuer"], "業務スーパー桃谷店")
        self.assertEqual(context["amount"], "5860")
        self.assertEqual(context["registration_number"], ["T9122001020907"])
        self.assertIn("購入用途", context["review_points"])
        self.assertNotIn("issuer", context["low_confidence_fields"])
        self.assertEqual(context["prompt_ocr_result"]["data"]["issuer"], "業務スーパー桃谷店")
        self.assertNotIn("positions", str(context["prompt_ocr_result"]))
        self.assertEqual(context["text_signals"], ["業務スーパー桃谷店"])

    def test_account_classification_query_includes_key_receipt_fields(self):
        context = extract_receipt_classification_context(SAMPLE_OCR_RESULT)

        query = build_account_classification_query(context)

        self.assertIn("勘定科目", query)
        self.assertIn("業務スーパー桃谷店", query)
        self.assertIn("5860", query)
        self.assertIn("2026-01-13", query)

    def test_prompt_contains_ocr_json_and_context(self):
        context = extract_receipt_classification_context(SAMPLE_OCR_RESULT)
        prompt = build_account_classification_prompt(
            context,
            [
                SimpleNamespace(
                    chunk_id="doc-1:0",
                    document_id="doc-1",
                    filename="勘定科目表.pdf",
                    page_number=3,
                    chunk_index=0,
                    text="会議に伴う飲食費は会議費として処理する。",
                )
            ],
            candidate_titles=["会議費", "事務用消耗品費"],
        )

        self.assertIn('"issuer": "業務スーパー桃谷店"', prompt)
        self.assertIn("[1] 勘定科目表.pdf p.3", prompt)
        self.assertIn("必ずJSONオブジェクトのみを返してください", prompt)
        self.assertIn("座標情報などは除外済み", prompt)
        self.assertIn('"事務用消耗品費"', prompt)

    def test_extract_account_title_candidates_from_hits_reads_exact_titles(self):
        hits = [
            SimpleNamespace(
                text=(
                    "711 役員報酬 役員報酬 取締役への報酬。\n"
                    "737 消耗品費 消耗品費 文房具・コピー用紙など。\n"
                    "754 事務用消耗品費 事務用消耗品費 コピー用紙・文房具など。"
                )
            )
        ]

        titles = extract_account_title_candidates_from_hits(hits)

        self.assertEqual(titles[:2], ["消耗品費", "事務用消耗品費"])
        self.assertNotIn("役員報酬", titles)

    def test_normalize_to_candidate_title_uses_pdf_name(self):
        normalized = normalize_to_candidate_title(
            "交際費",
            ["交際接待費", "会議費", "雑費"],
        )

        self.assertEqual(normalized, "交際接待費")

    def test_build_candidate_alternatives_uses_only_pdf_titles(self):
        alternatives = build_candidate_alternatives(
            llm_alternatives=["事務用消耗品", "役員報酬", "雑費", "会議費"],
            candidate_titles=["福利厚生費", "事務用消耗品費", "会議費", "雑費"],
        )

        self.assertEqual(alternatives, ["事務用消耗品費", "雑費", "会議費"])

    def test_normalize_to_candidate_title_returns_empty_without_pdf_candidates(self):
        normalized = normalize_to_candidate_title("消耗品費", [])

        self.assertEqual(normalized, "")


if __name__ == "__main__":
    unittest.main()
