"""Retriever step — finds relevant code chunks for the issue.

Input: ctx.issue, FAISS index at {repo_path}/.autopr_index/
Output: populates ctx.retrieved_chunks with top-8 chunks ranked by cosine similarity

Query = issue title + first 200 chars of body
Deduplication: keep highest-score chunk per file, max 4 files
"""

import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning)

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from agent.context import RunContext, RetrievedChunk, StepError

INDEX_DIR = ".autopr_index"
FAISS_FILE = "index.faiss"
CHUNKS_FILE = "chunks.json"
EMBED_MODEL = "all-MiniLM-L6-v2"

TOP_K = 8          # raw candidates to retrieve from FAISS
MAX_FILES = 4      # max distinct files after deduplication

# Module-level singleton — loaded once per process, reused across calls.
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def run(ctx: RunContext) -> None:
    """Retrieve relevant code chunks from the FAISS index.

    Queries the index using the issue title and body, returning
    the top chunks ranked by cosine similarity.

    Args:
        ctx: RunContext with ctx.issue and ctx.repo_path set.

    Mutates:
        ctx.retrieved_chunks: Populated with top-8 RetrievedChunk objects.

    Raises:
        StepError: If retrieval fails or index doesn't exist.
    """
    index_dir = Path(ctx.repo_path).resolve() / INDEX_DIR
    faiss_path = index_dir / FAISS_FILE
    chunks_path = index_dir / CHUNKS_FILE

    if not faiss_path.exists() or not chunks_path.exists():
        raise StepError(
            f"retriever: index not found at {index_dir} — run repo_indexer first"
        )

    # Load index and chunk metadata
    try:
        index = faiss.read_index(str(faiss_path))
        all_chunks: list[dict] = json.loads(chunks_path.read_text())
    except Exception as e:
        raise StepError(f"retriever: failed to load index: {e}") from e

    # Build query string
    query = f"{ctx.issue.title}\n{ctx.issue.body[:200]}"

    # Embed query with the same model used at index time
    try:
        query_vec = _get_model().encode([query], normalize_embeddings=True)
        query_vec = np.array(query_vec, dtype="float32")
    except Exception as e:
        raise StepError(f"retriever: embedding failed: {e}") from e

    # Search — retrieve more candidates than needed so dedup has room to work
    n_candidates = min(TOP_K * MAX_FILES, index.ntotal)
    scores, indices = index.search(query_vec, n_candidates)

    # Deduplicate: keep highest-scoring chunk per file, then cap at MAX_FILES
    best_per_file: dict[str, tuple[float, dict]] = {}
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        chunk = all_chunks[idx]
        file_key = chunk["file"]
        if file_key not in best_per_file or score > best_per_file[file_key][0]:
            best_per_file[file_key] = (float(score), chunk)

    # Sort files by their best score descending, take top MAX_FILES
    top_files = sorted(best_per_file.values(), key=lambda t: t[0], reverse=True)[:MAX_FILES]

    ctx.retrieved_chunks = [
        RetrievedChunk(
            file=chunk["file"],
            symbol=chunk["symbol"],
            start_line=chunk["start_line"],
            end_line=chunk["end_line"],
            content=chunk["content"],
            score=score,
        )
        for score, chunk in top_files
    ]
