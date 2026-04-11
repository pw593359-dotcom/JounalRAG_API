from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from .config import Settings
from .dependencies import get_app_settings, get_rag_service, get_store
from .document_service import create_document_from_upload, delete_document, enqueue_reindex
from .elastic import ElasticRagStore
from .rag import RagService
from .schemas import (
    AnswerRequest,
    AnswerResponse,
    DocumentCreateResponse,
    DocumentOut,
    JobOut,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(prefix="/api", tags=["api"])


@router.post(
    "/documents",
    response_model=DocumentCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_document(
    file: UploadFile = File(...),
    metadata_json: str | None = Form(default=None),
    store: ElasticRagStore = Depends(get_store),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    document, job, task_id = create_document_from_upload(
        upload_file=file,
        metadata_json=metadata_json,
        store=store,
        settings=settings,
    )
    return {"document": document, "job": job, "task_id": task_id}


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(store: ElasticRagStore = Depends(get_store)) -> list[dict]:
    return store.list_documents()


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str,
    store: ElasticRagStore = Depends(get_store),
) -> dict:
    document = store.get_document(document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(
    document_id: str,
    store: ElasticRagStore = Depends(get_store),
    settings: Settings = Depends(get_app_settings),
) -> None:
    delete_document(document_id=document_id, store=store, settings=settings)


@router.post("/documents/{document_id}/reindex", response_model=JobOut)
def reindex_document(
    document_id: str,
    store: ElasticRagStore = Depends(get_store),
) -> dict:
    job, _task_id = enqueue_reindex(document_id=document_id, store=store)
    return job


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(store: ElasticRagStore = Depends(get_store)) -> list[dict]:
    return store.list_jobs()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, store: ElasticRagStore = Depends(get_store)) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return job


@router.post("/search", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    rag: RagService = Depends(get_rag_service),
) -> SearchResponse:
    return rag.search(
        query=payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
    )


@router.post("/answer", response_model=AnswerResponse)
def answer(
    payload: AnswerRequest,
    rag: RagService = Depends(get_rag_service),
) -> AnswerResponse:
    return rag.answer(
        query=payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
    )
