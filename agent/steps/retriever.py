"""Retriever step — finds relevant code chunks for the issue.

Input: ctx.issue, FAISS index at {repo_path}/.autopr_index/
Output: populates ctx.retrieved_chunks with RETRIEVER_TOP_K chunks (default 5)

Flow:
  1. FAISS cosine search returns top-20 candidates
  2. CrossEncoder reranks all 20 against full issue title + body
  3. Top RETRIEVER_TOP_K reranked results written to ctx.retrieved_chunks
  Fallback: if reranker fails, uses raw FAISS ordering instead of raising.
"""

import json
import logging
import os
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning)

import faiss
import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

from agent.context import RunContext, RetrievedChunk, StepError

INDEX_DIR = ".autopr_index"
FAISS_FILE = "index.faiss"
CHUNKS_FILE = "chunks.json"
EMBED_MODEL = "all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

FAISS_CANDIDATES = 20   # raw candidates fetched from FAISS before reranking

logger = logging.getLogger(__name__)

# Embedding model — lazy singleton, loaded on first run() call.
_embed_model: SentenceTransformer | None = None

# Reranker — instantiated at module level so it is loaded once per process.
# Wrapped in try/except so a missing model or network failure doesn't break imports.
_rerank_model: CrossEncoder | None = None
try:
    _rerank_model = CrossEncoder(RERANK_MODEL)
except Exception as _load_err:
    logger.warning("retriever: CrossEncoder failed to load at import: %s", _load_err)


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(EMBED_MODEL)
    return _embed_model


def run(ctx: RunContext) -> None:
    index_dir = Path(ctx.repo_path).resolve() / INDEX_DIR
    faiss_path = index_dir / FAISS_FILE
    chunks_path = index_dir / CHUNKS_FILE

    if not faiss_path.exists() or not chunks_path.exists():
        raise StepError(
            f"retriever: index not found at {index_dir} — run repo_indexer first"
        )

    try:
        index = faiss.read_index(str(faiss_path))
        all_chunks: list[dict] = json.loads(chunks_path.read_text())
    except Exception as e:
        raise StepError(f"retriever: failed to load index: {e}") from e

    # Embed with the same model used at index time (truncated body is fine for ANN search)
    embed_query = f"{ctx.issue.title}\n{ctx.issue.body[:200]}"
    try:
        query_vec = _get_embed_model().encode([embed_query], normalize_embeddings=True)
        query_vec = np.array(query_vec, dtype="float32")
    except Exception as e:
        raise StepError(f"retriever: embedding failed: {e}") from e

    # FAISS search — fetch up to FAISS_CANDIDATES raw results
    n_candidates = min(FAISS_CANDIDATES, index.ntotal)
    scores, indices = index.search(query_vec, n_candidates)

    candidates: list[tuple[float, dict]] = [
        (float(score), all_chunks[idx])
        for score, idx in zip(scores[0], indices[0])
        if idx >= 0 and all_chunks[idx].get("content", "").strip()
    ]

    top_k = int(os.getenv("RETRIEVER_TOP_K", "5"))

    # Cross-encoder rerank: score each candidate against full issue text
    rerank_query = f"{ctx.issue.title}\n\n{ctx.issue.body}"
    try:
        if _rerank_model is None:
            raise RuntimeError("reranker not loaded")

        pairs = [(rerank_query, chunk["content"]) for _, chunk in candidates]
        rerank_scores: list[float] = _rerank_model.predict(pairs).tolist()

        ranked = sorted(
            zip(rerank_scores, candidates),
            key=lambda t: t[0],
            reverse=True,
        )
        top = [(chunk, rerank_score) for rerank_score, (_, chunk) in ranked[:top_k]]

        best_label = f"{top[0][0]['file']}:{top[0][0]['start_line']}-{top[0][0]['end_line']}" if top else "none"
        ctx.step_log.append(
            f"retriever: reranked {len(candidates)} candidates → top match: {best_label}"
        )

    except Exception as exc:
        logger.warning("retriever: reranker failed (%s) — falling back to FAISS ordering", exc)
        ctx.step_log.append(
            f"retriever: reranker failed ({exc}) — using FAISS ordering"
        )
        # Fallback: use raw FAISS scores, preserve original (faiss_score, chunk) ordering
        top = [(chunk, faiss_score) for faiss_score, chunk in candidates[:top_k]]

    ctx.retrieved_chunks = [
        RetrievedChunk(
            file=chunk["file"],
            symbol=chunk["symbol"],
            start_line=chunk["start_line"],
            end_line=chunk["end_line"],
            content=chunk["content"],
            score=score,
        )
        for chunk, score in top
    ]
