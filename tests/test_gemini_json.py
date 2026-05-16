import unittest

from app.json_parsing import parse_json_object


class GeminiJsonParsingTests(unittest.TestCase):
    def test_parse_json_object_accepts_plain_json(self):
        payload = parse_json_object('{"account_title":"会議費","confidence":0.8}')

        self.assertEqual(payload["account_title"], "会議費")
        self.assertEqual(payload["confidence"], 0.8)

    def test_parse_json_object_accepts_fenced_json(self):
        payload = parse_json_object(
            '```json\n{"account_title":"交際費","confidence":0.7}\n```'
        )

        self.assertEqual(payload["account_title"], "交際費")

    def test_parse_json_object_extracts_json_with_prefix_text(self):
        payload = parse_json_object(
            '以下を返します。\n{"account_title":"消耗品費","confidence":0.6,"reason":"test"}'
        )

        self.assertEqual(payload["account_title"], "消耗品費")


if __name__ == "__main__":
    unittest.main()
