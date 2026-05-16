from contextlib import asynccontextmanager
import logging

import redis
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .admin import router as admin_router
from .api import router as api_router
from .dependencies import get_app_settings, get_store

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = get_store()
    try:
        store.ensure_indices()
    except Exception:
        logger.exception("Elasticsearch index setup failed")
    yield


app = FastAPI(
    title="Journal RAG API",
    description=(
        "PDF文書をElasticsearchへ登録して検索・回答生成を行うRAG APIです。"
        "あわせて、レシートOCR結果から勘定科目を推定するAPIも提供します。"
    ),
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(api_router)
app.include_router(admin_router)


@app.get(
    "/",
    summary="APIルート情報を取得",
    description="API名と、管理画面およびOpenAPIドキュメントへの入口を返します。",
)
def root() -> dict[str, str]:
    return {
        "name": "Journal RAG API",
        "admin": "/admin/documents",
        "docs": "/docs",
    }


@app.get(
    "/health",
    summary="ヘルスチェック",
    description="API本体、Elasticsearch、Redis の接続状態を返します。",
)
def health() -> dict[str, object]:
    settings = get_app_settings()
    store = get_store()

    elasticsearch_ok = False
    redis_ok = False
    try:
        elasticsearch_ok = store.ping()
    except Exception:
        logger.exception("Elasticsearch health check failed")

    try:
        redis_client = redis.from_url(settings.redis_url)
        redis_ok = bool(redis_client.ping())
    except Exception:
        logger.exception("Redis health check failed")

    status = "ok" if elasticsearch_ok and redis_ok else "degraded"
    return {
        "status": status,
        "elasticsearch": elasticsearch_ok,
        "redis": redis_ok,
        "environment": settings.environment,
    }
