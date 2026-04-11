import unittest
from types import SimpleNamespace

from app.prompting import build_answer_prompt


class RagPromptTests(unittest.TestCase):
    def test_prompt_includes_query_context_and_citation_marker(self):
        prompt = build_answer_prompt(
            "契約更新日は？",
            [
                SimpleNamespace(
                    chunk_id="doc-1:0",
                    document_id="doc-1",
                    filename="contract.pdf",
                    page_number=3,
                    chunk_index=0,
                    text="契約更新日は2026年4月1日です。",
                    score=1.2,
                    metadata={},
                )
            ],
        )

        self.assertIn("契約更新日は？", prompt)
        self.assertIn("[1] contract.pdf p.3", prompt)
        self.assertIn("契約更新日は2026年4月1日です。", prompt)


if __name__ == "__main__":
    unittest.main()
