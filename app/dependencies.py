from functools import lru_cache

from .config import Settings, get_settings
from .elastic import ElasticRagStore
from .gemini import GeminiService
from .rag import RagService


@lru_cache
def get_store() -> ElasticRagStore:
    return ElasticRagStore(get_settings())


@lru_cache
def get_gemini_service() -> GeminiService:
    return GeminiService(get_settings())


@lru_cache
def get_rag_service() -> RagService:
    return RagService(get_store(), get_gemini_service())


def get_app_settings() -> Settings:
    return get_settings()

