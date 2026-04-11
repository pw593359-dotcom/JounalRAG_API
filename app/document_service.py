import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from .config import Settings
from .elastic import ElasticRagStore, utc_now
from .storage import delete_document_files, save_upload_stream
from .tasks import ingest_document_task


def create_document_from_upload(
    *,
    upload_file: UploadFile,
    metadata_json: str | None,
    store: ElasticRagStore,
    settings: Settings,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    metadata = parse_metadata_json(metadata_json)
    document_id = str(uuid4())
    filename = upload_file.filename or "document.pdf"

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="初期版でアップロードできる文書はPDFのみです。",
        )

    source_path = save_upload_stream(
        upload_file.file,
        filename,
        document_id,
        settings.upload_dir,
    )
    document = store.create_document(
        document_id=document_id,
        filename=filename,
        content_type=upload_file.content_type,
        source_path=str(source_path),
        metadata=metadata,
    )
    job = store.create_job(document_id=document_id, operation="ingest")
    task_id: str | None = None

    try:
        task = ingest_document_task.delay(document_id, job["id"], str(source_path))
        task_id = task.id
        job = store.update_job(job["id"], task_id=task_id)
    except Exception as exc:
        error = f"Celeryジョブの投入に失敗しました: {exc}"
        store.update_document(document_id, status="failed", error=error)
        job = store.update_job(
            job["id"],
            status="failed",
            stage="enqueue",
            error=error,
            finished_at=utc_now(),
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error) from exc

    return document, job, task_id


def enqueue_reindex(
    *,
    document_id: str,
    store: ElasticRagStore,
) -> tuple[dict[str, Any], str | None]:
    document = store.get_document(document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    source_path = document.get("source_path")
    if not source_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="document source_path is missing",
        )

    store.update_document(document_id, status="queued", error=None)
    job = store.create_job(document_id=document_id, operation="reindex")
    task_id: str | None = None
    try:
        task = ingest_document_task.delay(document_id, job["id"], source_path)
        task_id = task.id
        job = store.update_job(job["id"], task_id=task_id)
    except Exception as exc:
        error = f"Celeryジョブの投入に失敗しました: {exc}"
        store.update_document(document_id, status="failed", error=error)
        job = store.update_job(
            job["id"],
            status="failed",
            stage="enqueue",
            error=error,
            finished_at=utc_now(),
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error) from exc
    return job, task_id


def delete_document(
    *,
    document_id: str,
    store: ElasticRagStore,
    settings: Settings,
) -> None:
    store.delete_document(document_id)
    delete_document_files(document_id, settings.upload_dir)


def parse_metadata_json(metadata_json: str | None) -> dict[str, Any]:
    if not metadata_json:
        return {}
    try:
        metadata = json.loads(metadata_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="metadata_json must be valid JSON",
        ) from exc
    if not isinstance(metadata, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="metadata_json must be a JSON object",
        )
    return metadata

