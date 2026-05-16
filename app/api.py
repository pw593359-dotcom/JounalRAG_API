from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, UploadFile, status

from .config import Settings
from .dependencies import get_app_settings, get_rag_service, get_store
from .document_service import create_document_from_upload, delete_document, enqueue_reindex
from .elastic import ElasticRagStore
from .rag import RagService
from .schemas import (
    AccountClassificationRequest,
    AccountClassificationResponse,
    AccountClassificationStoredOut,
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
    summary="PDF文書をアップロードして取り込みジョブを作成",
    description=(
        "PDFを登録し、バックグラウンドでテキスト抽出・チャンク分割・埋め込み生成・"
        "Elasticsearch登録を行うジョブを起票します。"
    ),
)
def upload_document(
    file: UploadFile = File(..., description="登録するPDFファイル"),
    metadata_json: str | None = Form(
        default=None,
        description="任意メタデータのJSON文字列",
        examples=['{"source":"manual","category":"finance"}'],
    ),
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


@router.get(
    "/documents",
    response_model=list[DocumentOut],
    summary="登録済み文書一覧を取得",
    description="RAGに登録されているPDF文書の一覧を返します。",
)
def list_documents(store: ElasticRagStore = Depends(get_store)) -> list[dict]:
    return store.list_documents()


@router.get(
    "/documents/{document_id}",
    response_model=DocumentOut,
    summary="文書詳細を取得",
    description="指定した文書IDの状態、ページ数、チャンク数などを返します。",
)
def get_document(
    document_id: str = Path(..., description="文書ID"),
    store: ElasticRagStore = Depends(get_store),
) -> dict:
    document = store.get_document(document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return document


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="文書を削除",
    description="文書本体、関連チャンク、関連ジョブを削除します。",
)
def remove_document(
    document_id: str = Path(..., description="文書ID"),
    store: ElasticRagStore = Depends(get_store),
    settings: Settings = Depends(get_app_settings),
) -> None:
    delete_document(document_id=document_id, store=store, settings=settings)


@router.post(
    "/documents/{document_id}/reindex",
    response_model=JobOut,
    summary="文書を再インデックス",
    description="既存文書を再抽出・再埋め込み・再登録するジョブを起票します。",
)
def reindex_document(
    document_id: str = Path(..., description="文書ID"),
    store: ElasticRagStore = Depends(get_store),
) -> dict:
    job, _task_id = enqueue_reindex(document_id=document_id, store=store)
    return job


@router.get(
    "/jobs",
    response_model=list[JobOut],
    summary="ジョブ一覧を取得",
    description="取り込みや再処理のバックグラウンドジョブ一覧を返します。",
)
def list_jobs(store: ElasticRagStore = Depends(get_store)) -> list[dict]:
    return store.list_jobs()


@router.get(
    "/jobs/{job_id}",
    response_model=JobOut,
    summary="ジョブ詳細を取得",
    description="指定したジョブIDの進行状態と結果を返します。",
)
def get_job(
    job_id: str = Path(..., description="ジョブID"),
    store: ElasticRagStore = Depends(get_store),
) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return job


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="RAG検索を実行",
    description="クエリを埋め込み化してElasticsearchでハイブリッド検索し、関連チャンクを返します。",
)
def search(
    payload: SearchRequest,
    rag: RagService = Depends(get_rag_service),
) -> SearchResponse:
    return rag.search(
        query=payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
    )


@router.post(
    "/answer",
    response_model=AnswerResponse,
    summary="RAG回答を生成",
    description="検索結果チャンクを根拠として、Geminiで自然文の回答を生成します。",
)
def answer(
    payload: AnswerRequest,
    rag: RagService = Depends(get_rag_service),
) -> AnswerResponse:
    return rag.answer(
        query=payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
    )


@router.post(
    "/account-classifications",
    response_model=AccountClassificationResponse,
    summary="領収書OCRから勘定科目を推定",
    description=(
        "OCR済みレシートJSONを受け取り、登録済みPDFを検索した上で、"
        "該当しそうな勘定科目を推定します。"
    ),
)
def classify_account(
    payload: AccountClassificationRequest,
    rag: RagService = Depends(get_rag_service),
) -> AccountClassificationResponse:
    return rag.classify_account(
        ocr_result=payload.ocr_result,
        top_k=payload.top_k,
        filters=payload.filters,
    )


@router.get(
    "/account-classifications/{classification_id}",
    response_model=AccountClassificationStoredOut,
    summary="保存済み勘定科目分類結果を取得",
    description="classification_id を指定して、保存済みの分類結果と元のOCR JSONを取得します。",
)
def get_account_classification(
    classification_id: str = Path(..., description="分類結果ID"),
    store: ElasticRagStore = Depends(get_store),
) -> AccountClassificationStoredOut:
    record = store.get_account_classification(classification_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="account classification not found",
        )
    result = dict(record.get("response") or {})
    result["classification_id"] = record["id"]
    return AccountClassificationStoredOut(
        classification_id=record["id"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        top_k=record.get("top_k") or 0,
        filters=record.get("filters") or {},
        ocr_result=record.get("ocr_result") or {},
        result=AccountClassificationResponse(**result),
    )
