from pathlib import Path

from .celery_app import celery_app
from .chunking import chunk_pages
from .config import get_settings
from .elastic import ElasticRagStore, utc_now
from .gemini import GeminiService
from .pdf import extract_pdf_pages


@celery_app.task(name="app.tasks.ingest_document_task")
def ingest_document_task(document_id: str, job_id: str, source_path: str) -> dict[str, str]:
    settings = get_settings()
    store = ElasticRagStore(settings)
    gemini = GeminiService(settings)

    try:
        document = store.get_document(document_id)
        if not document:
            raise ValueError(f"document not found: {document_id}")

        store.update_job(job_id, status="running", stage="extracting", progress=10)
        store.update_document(document_id, status="processing", error=None)

        pages = extract_pdf_pages(Path(source_path))
        text_chunks = chunk_pages(
            pages,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        if not text_chunks:
            raise ValueError("チャンク化できるテキストがありません。")

        store.update_job(job_id, stage="embedding", progress=45)
        embeddings = gemini.embed_texts([chunk.text for chunk in text_chunks])

        store.update_job(job_id, stage="indexing", progress=80)
        now = utc_now()
        chunk_documents = [
            {
                "chunk_id": f"{document_id}:{chunk.chunk_index}",
                "document_id": document_id,
                "filename": document["filename"],
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "embedding": embedding,
                "metadata": document.get("metadata") or {},
                "created_at": now,
            }
            for chunk, embedding in zip(text_chunks, embeddings, strict=True)
        ]
        store.replace_chunks(document_id, chunk_documents)

        full_text = "\n\n".join(page.text for page in pages)
        store.update_document(
            document_id,
            status="ready",
            page_count=len(pages),
            chunk_count=len(chunk_documents),
            text_preview=full_text[:2000],
            error=None,
        )
        store.update_job(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            finished_at=utc_now(),
        )
        return {"document_id": document_id, "job_id": job_id}

    except Exception as exc:
        error = str(exc)
        store.update_document(document_id, status="failed", error=error)
        store.update_job(
            job_id,
            status="failed",
            stage="failed",
            error=error,
            finished_at=utc_now(),
        )
        raise

