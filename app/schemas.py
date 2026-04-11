from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str | None = None
    status: str
    page_count: int | None = None
    chunk_count: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    text_preview: str | None = None
    error: str | None = None
    created_at: datetime | str
    updated_at: datetime | str


class JobOut(BaseModel):
    id: str
    document_id: str
    operation: str
    status: str
    stage: str | None = None
    progress: int = 0
    task_id: str | None = None
    error: str | None = None
    created_at: datetime | str
    updated_at: datetime | str
    finished_at: datetime | str | None = None


class DocumentCreateResponse(BaseModel):
    document: DocumentOut
    job: JobOut
    task_id: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, Any] = Field(default_factory=dict)


class SearchHit(BaseModel):
    chunk_id: str
    document_id: str
    filename: str | None = None
    page_number: int | None = None
    chunk_index: int
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


class AnswerRequest(SearchRequest):
    pass


class AnswerResponse(BaseModel):
    query: str
    answer: str
    citations: list[SearchHit]

