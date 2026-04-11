import unittest

from app.chunking import TextPage, chunk_pages, split_text


class SplitTextTests(unittest.TestCase):
    def test_empty_text_returns_empty_list(self):
        self.assertEqual(split_text("   "), [])

    def test_chunks_stay_within_limit_for_long_text(self):
        chunks = split_text("あ" * 2500, chunk_size=1000, chunk_overlap=150)

        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))

    def test_chunk_pages_keeps_page_numbers_and_global_indexes(self):
        pages = [
            TextPage(page_number=1, text="a" * 12),
            TextPage(page_number=2, text="b" * 12),
        ]

        chunks = chunk_pages(pages, chunk_size=10, chunk_overlap=2)

        self.assertEqual([chunk.chunk_index for chunk in chunks], [0, 1, 2, 3])
        self.assertEqual([chunk.page_number for chunk in chunks], [1, 1, 2, 2])


if __name__ == "__main__":
    unittest.main()

