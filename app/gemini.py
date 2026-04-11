from collections.abc import Sequence

from .config import Settings


class GeminiService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        client = self._get_client()
        from google.genai import types

        response = client.models.embed_content(
            model=self.settings.gemini_embedding_model,
            contents=list(texts),
            config=types.EmbedContentConfig(
                output_dimensionality=self.settings.embedding_dimensions,
            ),
        )
        embeddings = getattr(response, "embeddings", None)
        if embeddings is None:
            embedding = getattr(response, "embedding", None)
            if embedding is None:
                raise RuntimeError("Gemini embedding response did not include embeddings")
            embeddings = [embedding]

        vectors = [list(item.values) for item in embeddings]
        if len(vectors) != len(texts):
            raise RuntimeError("Gemini embedding response count did not match input count")
        return vectors

    def generate_answer(self, prompt: str) -> str:
        client = self._get_client()
        response = client.models.generate_content(
            model=self.settings.gemini_generation_model,
            contents=prompt,
        )
        text = getattr(response, "text", None)
        if text:
            return text.strip()
        return str(response).strip()

    def _get_client(self):
        if not self.settings.gemini_api_key:
            raise RuntimeError("RAG_GEMINI_API_KEY is required")
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

