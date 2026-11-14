"""all-MiniLM-L6-v2 sentence embeddings (384-dim), identical locally and on Render.

The book library (knowledge_base) was embedded with all-MiniLM-L6-v2, so dream
queries must use the same model for similarity scores to mean anything.

Backend preference:
  1. fastembed (ONNX runtime, no PyTorch, ~150-200 MB RAM) — works on Render's free tier.
  2. sentence-transformers (PyTorch) — local fallback if fastembed is not installed.
No API calls, so embeddings never spend Gemini credits.
"""

import logging
import threading

logger = logging.getLogger(__name__)

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_lock = threading.Lock()
_backend = None  # ("fastembed", model) | ("sentence-transformers", model)


def _load():
    global _backend
    with _lock:
        if _backend is not None:
            return _backend
        try:
            from fastembed import TextEmbedding

            _backend = ("fastembed", TextEmbedding(_MODEL_NAME))
            logger.info("Embeddings: fastembed (%s)", _MODEL_NAME)
        except ImportError:
            from sentence_transformers import SentenceTransformer

            _backend = ("sentence-transformers", SentenceTransformer("all-MiniLM-L6-v2"))
            logger.info("Embeddings: sentence-transformers (all-MiniLM-L6-v2)")
        return _backend


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed several texts in one pass (L2-normalised, 384 floats each)."""
    if not texts:
        return []
    kind, model = _load()
    if kind == "fastembed":
        return [vector.tolist() for vector in model.embed(texts)]
    return [vector.tolist() for vector in model.encode(texts, normalize_embeddings=True)]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
