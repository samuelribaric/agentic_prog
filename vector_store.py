"""ChromaDB wrapper for benchmark storage and retrieval."""

from __future__ import annotations

import json
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

import config

_collection_name = "benchmarks"


def _get_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(
        model=config.EMBEDDING_MODEL,
        base_url=config.OLLAMA_BASE_URL,
    )


def get_vector_store() -> Chroma:
    """Return a persistent Chroma vector store for benchmarks."""
    return Chroma(
        collection_name=_collection_name,
        embedding_function=_get_embeddings(),
        persist_directory=config.CHROMA_PERSIST_DIR,
    )


def store_benchmarks(candidates: list[dict]) -> None:
    """Store candidate model benchmark data as documents in ChromaDB."""
    if not candidates:
        return

    vs = get_vector_store()
    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    for c in candidates:
        doc_text = (
            f"Model: {c.get('name', 'unknown')}\n"
            f"Provider: {c.get('provider', 'unknown')}\n"
            f"Parameters: {c.get('parameters', 'unknown')}\n"
            f"Strengths: {', '.join(c.get('strengths', []))}\n"
            f"Weaknesses: {', '.join(c.get('weaknesses', []))}\n"
            f"Benchmarks: {json.dumps(c.get('benchmarks', {}))}\n"
            f"Pricing: {c.get('pricing', 'unknown')}\n"
            f"Notes: {c.get('notes', '')}"
        )
        documents.append(doc_text)
        metadatas.append({
            "model_name": c.get("name", "unknown"),
            "provider": c.get("provider", "unknown"),
        })
        ids.append(f"model-{c.get('name', 'unknown').replace(' ', '-').lower()}")

    vs.add_texts(texts=documents, metadatas=metadatas, ids=ids)


def query_benchmarks(query: str, k: int = 5) -> list[str]:
    """Query ChromaDB for benchmark data relevant to the query."""
    vs = get_vector_store()
    try:
        docs = vs.similarity_search(query, k=k)
        return [doc.page_content for doc in docs]
    except Exception:
        return []
