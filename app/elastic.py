from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from elasticsearch import Elasticsearch, NotFoundError, helpers

from .config import Settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ElasticRagStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        kwargs: dict[str, Any] = {
            "hosts": [settings.elasticsearch_url],
            "request_timeout": settings.elasticsearch_request_timeout,
        }
        if settings.elasticsearch_user and settings.elasticsearch_password:
            kwargs["basic_auth"] = (
                settings.elasticsearch_user,
                settings.elasticsearch_password,
            )
        self.client = Elasticsearch(**kwargs)

    def ping(self) -> bool:
        return bool(self.client.ping())

    def ensure_indices(self) -> None:
        self._ensure_documents_index()
        self._ensure_chunks_index()
        self._ensure_jobs_index()

    def create_document(
        self,
        *,
        document_id: str | None,
        filename: str,
        content_type: str | None,
        source_path: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        document_id = document_id or str(uuid4())
        now = utc_now()
        source = {
            "document_id": document_id,
            "filename": filename,
            "content_type": content_type,
            "source_path": source_path,
            "status": "queued",
            "page_count": None,
            "chunk_count": 0,
            "metadata": metadata,
            "text_preview": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        self.client.index(
            index=self.settings.documents_index,
            id=document_id,
            document=source,
            refresh=True,
        )
        return self._with_id(document_id, source)

    def update_document(self, document_id: str, **fields: Any) -> dict[str, Any]:
        fields["updated_at"] = utc_now()
        self.client.update(
            index=self.settings.documents_index,
            id=document_id,
            doc=fields,
            refresh=True,
        )
        document = self.get_document(document_id)
        if not document:
            raise KeyError(f"document not found: {document_id}")
        return document

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        try:
            response = self.client.get(index=self.settings.documents_index, id=document_id)
        except NotFoundError:
            return None
        return self._with_id(response["_id"], response["_source"])

    def list_documents(self, size: int = 100) -> list[dict[str, Any]]:
        response = self.client.search(
            index=self.settings.documents_index,
            query={"match_all": {}},
            sort=[{"created_at": {"order": "desc"}}],
            size=size,
        )
        return [self._with_id(hit["_id"], hit["_source"]) for hit in response["hits"]["hits"]]

    def delete_document(self, document_id: str) -> None:
        self.client.options(ignore_status=[404]).delete(
            index=self.settings.documents_index,
            id=document_id,
            refresh=True,
        )
        self.client.delete_by_query(
            index=self.settings.chunks_index,
            query={"term": {"document_id": document_id}},
            conflicts="proceed",
            refresh=True,
        )
        self.client.delete_by_query(
            index=self.settings.jobs_index,
            query={"term": {"document_id": document_id}},
            conflicts="proceed",
            refresh=True,
        )

    def create_job(self, *, document_id: str, operation: str) -> dict[str, Any]:
        job_id = str(uuid4())
        now = utc_now()
        source = {
            "job_id": job_id,
            "document_id": document_id,
            "operation": operation,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "task_id": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "finished_at": None,
        }
        self.client.index(
            index=self.settings.jobs_index,
            id=job_id,
            document=source,
            refresh=True,
        )
        return self._with_id(job_id, source)

    def update_job(self, job_id: str, **fields: Any) -> dict[str, Any]:
        fields["updated_at"] = utc_now()
        self.client.update(
            index=self.settings.jobs_index,
            id=job_id,
            doc=fields,
            refresh=True,
        )
        job = self.get_job(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        return job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        try:
            response = self.client.get(index=self.settings.jobs_index, id=job_id)
        except NotFoundError:
            return None
        return self._with_id(response["_id"], response["_source"])

    def list_jobs(
        self,
        *,
        document_id: str | None = None,
        size: int = 100,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any]
        if document_id:
            query = {"term": {"document_id": document_id}}
        else:
            query = {"match_all": {}}
        response = self.client.search(
            index=self.settings.jobs_index,
            query=query,
            sort=[{"created_at": {"order": "desc"}}],
            size=size,
        )
        return [self._with_id(hit["_id"], hit["_source"]) for hit in response["hits"]["hits"]]

    def replace_chunks(self, document_id: str, chunks: list[dict[str, Any]]) -> None:
        self.clear_chunks(document_id)
        if not chunks:
            return
        actions = [
            {
                "_op_type": "index",
                "_index": self.settings.chunks_index,
                "_id": chunk["chunk_id"],
                "_source": chunk,
            }
            for chunk in chunks
        ]
        helpers.bulk(self.client, actions, refresh=True)

    def clear_chunks(self, document_id: str) -> None:
        self.client.delete_by_query(
            index=self.settings.chunks_index,
            query={"term": {"document_id": document_id}},
            conflicts="proceed",
            refresh=True,
        )

    def get_chunks(self, document_id: str, size: int = 50) -> list[dict[str, Any]]:
        response = self.client.search(
            index=self.settings.chunks_index,
            query={"term": {"document_id": document_id}},
            sort=[{"chunk_index": {"order": "asc"}}],
            size=size,
        )
        return [self._with_id(hit["_id"], hit["_source"]) for hit in response["hits"]["hits"]]

    def hybrid_search(
        self,
        *,
        query_text: str,
        vector: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        es_filters = self._build_filters(filters or {})
        bool_query: dict[str, Any] = {
            "bool": {
                "should": [
                    {
                        "match": {
                            "text": {
                                "query": query_text,
                                "boost": 0.4,
                            }
                        }
                    }
                ],
                "filter": es_filters,
            }
        }
        knn: dict[str, Any] = {
            "field": "embedding",
            "query_vector": vector,
            "k": top_k,
            "num_candidates": max(100, top_k * 10),
        }
        if es_filters:
            knn["filter"] = es_filters

        source_fields = [
            "chunk_id",
            "document_id",
            "filename",
            "page_number",
            "chunk_index",
            "text",
            "metadata",
        ]
        try:
            response = self.client.search(
                index=self.settings.chunks_index,
                query=bool_query,
                knn=knn,
                size=top_k,
                _source=source_fields,
            )
        except Exception:
            response = self.client.search(
                index=self.settings.chunks_index,
                query=self._script_score_query(query_text, vector, es_filters),
                size=top_k,
                _source=source_fields,
            )

        return [self._search_hit(hit) for hit in response["hits"]["hits"]]

    def _ensure_documents_index(self) -> None:
        if self.client.indices.exists(index=self.settings.documents_index):
            return
        self.client.indices.create(
            index=self.settings.documents_index,
            mappings={
                "properties": {
                    "document_id": {"type": "keyword"},
                    "filename": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "content_type": {"type": "keyword"},
                    "source_path": {"type": "keyword", "index": False},
                    "status": {"type": "keyword"},
                    "page_count": {"type": "integer"},
                    "chunk_count": {"type": "integer"},
                    "metadata": {"type": "object", "enabled": True},
                    "text_preview": {"type": "text"},
                    "error": {"type": "text"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                }
            },
        )

    def _ensure_chunks_index(self) -> None:
        if self.client.indices.exists(index=self.settings.chunks_index):
            return
        self.client.indices.create(
            index=self.settings.chunks_index,
            mappings={
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "filename": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "page_number": {"type": "integer"},
                    "chunk_index": {"type": "integer"},
                    "text": {"type": "text"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": self.settings.embedding_dimensions,
                        "index": True,
                        "similarity": "cosine",
                    },
                    "metadata": {"type": "object", "enabled": True},
                    "created_at": {"type": "date"},
                }
            },
        )

    def _ensure_jobs_index(self) -> None:
        if self.client.indices.exists(index=self.settings.jobs_index):
            return
        self.client.indices.create(
            index=self.settings.jobs_index,
            mappings={
                "properties": {
                    "job_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "operation": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "stage": {"type": "keyword"},
                    "progress": {"type": "integer"},
                    "task_id": {"type": "keyword"},
                    "error": {"type": "text"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "finished_at": {"type": "date"},
                }
            },
        )

    def _build_filters(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        clauses: list[dict[str, Any]] = []
        for key, value in filters.items():
            if value is None:
                continue
            if key in {"document_id", "status", "filename.keyword"}:
                field = key
            elif key == "filename":
                field = "filename.keyword"
            elif key.startswith("metadata."):
                field = key
            else:
                field = f"metadata.{key}.keyword"
            clauses.append({"term": {field: value}})
        return clauses

    def _script_score_query(
        self,
        query_text: str,
        vector: list[float],
        filters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "script_score": {
                "query": {
                    "bool": {
                        "should": [{"match": {"text": {"query": query_text, "boost": 0.4}}}],
                        "filter": filters,
                    }
                },
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0 + (_score * 0.01)",
                    "params": {"query_vector": vector},
                },
            }
        }

    def _search_hit(self, hit: dict[str, Any]) -> dict[str, Any]:
        source = hit["_source"]
        return {
            "chunk_id": source["chunk_id"],
            "document_id": source["document_id"],
            "filename": source.get("filename"),
            "page_number": source.get("page_number"),
            "chunk_index": source["chunk_index"],
            "text": source["text"],
            "score": hit.get("_score") or 0.0,
            "metadata": source.get("metadata") or {},
        }

    def _with_id(self, document_id: str, source: dict[str, Any]) -> dict[str, Any]:
        return {"id": document_id, **source}

