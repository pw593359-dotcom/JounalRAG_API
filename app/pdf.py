from pathlib import Path

from pypdf import PdfReader

from .chunking import TextPage


class PdfExtractionError(RuntimeError):
    pass


def extract_pdf_pages(path: Path) -> list[TextPage]:
    reader = PdfReader(str(path))
    pages: list[TextPage] = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(TextPage(page_number=index, text=text))

    if not pages:
        raise PdfExtractionError("PDFからテキストを抽出できませんでした。OCRは初期版の対象外です。")

    return pages

