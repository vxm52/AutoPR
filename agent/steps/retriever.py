"""Retriever step — finds relevant code chunks for the issue.

Input: ctx.issue, FAISS index at {repo_path}/.autopr_index/
Output: populates ctx.retrieved_chunks with RETRIEVER_TOP_K chunks (default 5)

Flow:
  1. FAISS cosine search returns top-20 candidates
  2. CrossEncoder reranks all 20 against full issue title + body
  3. Top RETRIEVER_TOP_K reranked results written to ctx.retrieved_chunks
  Fallback: if reranker fails, uses raw FAISS ordering instead of raising.

The core is the pure `retrieve()` function, which `run(ctx)` delegates to so
the evaluation harness (evals/) measures the exact same code path production
uses. `run(ctx)` only pulls inputs from env/ctx and formats step_log strings.
"""

import json
import logging
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
FAISS_QUERY_CHARS = 200  # body chars used for the ANN query (rerank uses full body)

logger = logging.getLogger(__name__)

# Embedding model — lazy singleton, loaded on first use.
_embed_model: SentenceTransformer | None = None

# Reranker — lazy singleton. Loaded on first use rather than at import so the
# harness can run reranker-free configs (use_reranker=False) without paying the
# model load, and so an offline/uncached model degrades to the FAISS fallback
# at call time instead of breaking the import.
_rerank_model: CrossEncoder | None = None
_rerank_load_attempted = False


@dataclass
class RetrievalResult:
    """Outcome of a single `retrieve()` call.

    chunks:          final top_k chunks (reranked, or FAISS order on fallback)
    candidate_count: number of non-empty FAISS candidates considered
    reranker_failed: True if use_reranker was requested but the reranker was
                     unavailable/errored and the result fell back to FAISS order
    exc:             the exception that triggered the fallback, if any
    """

    chunks: list[RetrievedChunk]
    candidate_count: int
    reranker_failed: bool = False
    exc: Optional[Exception] = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(EMBED_MODEL)
    return _embed_model


def _get_rerank_model() -> Optional[CrossEncoder]:
    """Lazily load the CrossEncoder. Returns None if it cannot be loaded."""
    global _rerank_model, _rerank_load_attempted
    if not _rerank_load_attempted:
        _rerank_load_attempted = True
        try:
            _rerank_model = CrossEncoder(RERANK_MODEL)
        except Exception as load_err:
            logger.warning("retriever: CrossEncoder failed to load: %s", load_err)
            _rerank_model = None
    return _rerank_model


def _load_index(repo_path: str) -> tuple["faiss.Index", list[dict]]:
    """Load the FAISS index and chunk metadata for a repo. Raises StepError."""
    index_dir = Path(repo_path).resolve() / INDEX_DIR
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

    return index, all_chunks


def _faiss_candidates(
    index: "faiss.Index",
    all_chunks: list[dict],
    embed_query: str,
    candidate_k: int,
) -> list[tuple[float, dict]]:
    """Embed the query and return up to candidate_k (faiss_score, chunk) pairs,
    filtering out empty-content chunks, preserving FAISS score order."""
    try:
        query_vec = _get_embed_model().encode([embed_query], normalize_embeddings=True)
        query_vec = np.array(query_vec, dtype="float32")
    except Exception as e:
        raise StepError(f"retriever: embedding failed: {e}") from e

    n_candidates = min(candidate_k, index.ntotal)
    scores, indices = index.search(query_vec, n_candidates)

    return [
        (float(score), all_chunks[idx])
        for score, idx in zip(scores[0], indices[0])
        if idx >= 0 and all_chunks[idx].get("content", "").strip()
    ]


def _rerank(
    rerank_query: str,
    candidates: list[tuple[float, dict]],
    model: CrossEncoder,
    top_k: int,
) -> list[tuple[dict, float]]:
    """Score candidates with the CrossEncoder and return top_k (chunk, score),
    highest score first."""
    pairs = [(rerank_query, chunk["content"]) for _, chunk in candidates]
    rerank_scores: list[float] = model.predict(pairs).tolist()

    ranked = sorted(
        zip(rerank_scores, candidates),
        key=lambda t: t[0],
        reverse=True,
    )
    return [(chunk, rerank_score) for rerank_score, (_, chunk) in ranked[:top_k]]


def _to_chunks(pairs: list[tuple[dict, float]]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            file=chunk["file"],
            symbol=chunk["symbol"],
            start_line=chunk["start_line"],
            end_line=chunk["end_line"],
            content=chunk["content"],
            score=score,
        )
        for chunk, score in pairs
    ]


def retrieve(
    issue_title: str,
    issue_body: str,
    repo_path: str,
    *,
    top_k: int = 5,
    candidate_k: int = FAISS_CANDIDATES,
    use_reranker: bool = True,
    faiss_query_chars: Optional[int] = FAISS_QUERY_CHARS,
) -> RetrievalResult:
    """Retrieve the top_k code chunks for an issue from the on-disk FAISS index.

    Pure function — reads the index, does not touch RunContext or env. This is
    the single retrieval code path shared by the pipeline and the eval harness.

    Args:
        issue_title:       issue title (used in both ANN and rerank queries).
        issue_body:        issue body.
        repo_path:         repo whose {repo_path}/.autopr_index/ will be read.
        top_k:             number of chunks to return.
        candidate_k:       raw FAISS candidates fetched before reranking.
        use_reranker:      if False, skip the CrossEncoder entirely and return
                           raw FAISS ordering.
        faiss_query_chars: truncate the body to this many chars for the ANN
                           query only (rerank always uses the full body). None
                           means use the full body for the ANN query too.

    Returns:
        RetrievalResult with the chunks and metadata about the reranker outcome.
    """
    index, all_chunks = _load_index(repo_path)

    body_for_embed = issue_body if faiss_query_chars is None else issue_body[:faiss_query_chars]
    embed_query = f"{issue_title}\n{body_for_embed}"
    rerank_query = f"{issue_title}\n\n{issue_body}"

    candidates = _faiss_candidates(index, all_chunks, embed_query, candidate_k)
    candidate_count = len(candidates)

    if not use_reranker:
        top = [(chunk, faiss_score) for faiss_score, chunk in candidates[:top_k]]
        return RetrievalResult(_to_chunks(top), candidate_count)

    # Cross-encoder rerank; fall back to raw FAISS ordering if it is unavailable.
    try:
        model = _get_rerank_model()
        if model is None:
            raise RuntimeError("reranker not loaded")
        top = _rerank(rerank_query, candidates, model, top_k)
        return RetrievalResult(_to_chunks(top), candidate_count)
    except Exception as exc:
        logger.warning(
            "retriever: reranker failed (%s) — falling back to FAISS ordering", exc
        )
        top = [(chunk, faiss_score) for faiss_score, chunk in candidates[:top_k]]
        return RetrievalResult(_to_chunks(top), candidate_count, reranker_failed=True, exc=exc)


def run(ctx: RunContext) -> None:
    top_k = int(os.getenv("RETRIEVER_TOP_K", "5"))

    result = retrieve(
        ctx.issue.title,
        ctx.issue.body,
        ctx.repo_path,
        top_k=top_k,
        candidate_k=FAISS_CANDIDATES,
        use_reranker=True,
        faiss_query_chars=FAISS_QUERY_CHARS,
    )

    ctx.retrieved_chunks = result.chunks

    if result.reranker_failed:
        ctx.step_log.append(
            f"retriever: reranker failed ({result.exc}) — using FAISS ordering"
        )
    else:
        top = result.chunks
        best_label = (
            f"{top[0].file}:{top[0].start_line}-{top[0].end_line}" if top else "none"
        )
        ctx.step_log.append(
            f"retriever: reranked {result.candidate_count} candidates → top match: {best_label}"
        )
