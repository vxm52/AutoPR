"""Repo indexer step — builds/updates the FAISS index for code retrieval.

Input: ctx.repo_path (local clone path)
Output: builds/updates the FAISS index on disk at {repo_path}/.autopr_index/

Chunking strategy:
- Chunk by function/class boundary using tree-sitter (preferred)
- Fall back to fixed 100-line windows with 20-line overlap
- Each chunk metadata: {file, symbol, start_line, end_line, content, language}

Skipped paths: node_modules/, __pycache__/, .git/, binary files, files > 500 lines

Index is cached — skip re-indexing if the index already exists and files are unchanged.
"""

from agent.context import RunContext


def run(ctx: RunContext) -> None:
    """Build or update the FAISS index for the repository.

    Creates embeddings for code chunks and stores them in a FAISS index
    at {repo_path}/.autopr_index/. Skips re-indexing if cache is fresh.

    Args:
        ctx: RunContext with ctx.repo_path set to the local clone path.

    Mutates:
        Writes index files to disk at {ctx.repo_path}/.autopr_index/

    Raises:
        StepError: If indexing fails.
    """
    raise NotImplementedError("repo_indexer.run not yet implemented")
