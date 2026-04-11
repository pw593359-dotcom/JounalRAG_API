from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .config import Settings
from .dependencies import get_app_settings, get_rag_service, get_store
from .document_service import create_document_from_upload, delete_document, enqueue_reindex
from .elastic import ElasticRagStore
from .rag import RagService

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def admin_root() -> RedirectResponse:
    return RedirectResponse(url="/admin/documents", status_code=303)


@router.get("/documents")
def documents_page(
    request: Request,
    store: ElasticRagStore = Depends(get_store),
):
    return templates.TemplateResponse(
        request,
        "documents.html",
        {
            "documents": store.list_documents(),
        },
    )


@router.post("/documents")
def upload_document(
    file: UploadFile = File(...),
    metadata_json: str = Form(default="{}"),
    store: ElasticRagStore = Depends(get_store),
    settings: Settings = Depends(get_app_settings),
) -> RedirectResponse:
    create_document_from_upload(
        upload_file=file,
        metadata_json=metadata_json,
        store=store,
        settings=settings,
    )
    return RedirectResponse(url="/admin/documents", status_code=303)


@router.get("/documents/{document_id}")
def document_detail(
    document_id: str,
    request: Request,
    store: ElasticRagStore = Depends(get_store),
):
    document = store.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="document not found")
    return templates.TemplateResponse(
        request,
        "document_detail.html",
        {
            "document": document,
            "chunks": store.get_chunks(document_id),
            "jobs": store.list_jobs(document_id=document_id),
        },
    )


@router.post("/documents/{document_id}/delete")
def delete_document_action(
    document_id: str,
    store: ElasticRagStore = Depends(get_store),
    settings: Settings = Depends(get_app_settings),
) -> RedirectResponse:
    delete_document(document_id=document_id, store=store, settings=settings)
    return RedirectResponse(url="/admin/documents", status_code=303)


@router.post("/documents/{document_id}/reindex")
def reindex_document_action(
    document_id: str,
    store: ElasticRagStore = Depends(get_store),
) -> RedirectResponse:
    enqueue_reindex(document_id=document_id, store=store)
    return RedirectResponse(url=f"/admin/documents/{document_id}", status_code=303)


@router.get("/jobs")
def jobs_page(
    request: Request,
    store: ElasticRagStore = Depends(get_store),
):
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "jobs": store.list_jobs(),
        },
    )


@router.get("/search")
def search_page(request: Request):
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "query": "",
            "top_k": 5,
            "result": None,
            "error": None,
        },
    )


@router.post("/search")
def search_action(
    request: Request,
    query: str = Form(...),
    top_k: int = Form(default=5),
    mode: str = Form(default="answer"),
    rag: RagService = Depends(get_rag_service),
):
    result = None
    error = None
    try:
        if mode == "search":
            result = rag.search(query=query, top_k=top_k, filters={})
        else:
            result = rag.answer(query=query, top_k=top_k, filters={})
    except Exception as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "query": query,
            "top_k": top_k,
            "mode": mode,
            "result": result,
            "error": error,
        },
    )
