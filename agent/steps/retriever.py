"""Retriever step — finds relevant code chunks for the issue.

Input: ctx.issue, FAISS index at {repo_path}/.autopr_index/
Output: populates ctx.retrieved_chunks with top-8 chunks ranked by cosine similarity

Query = issue title + first 200 chars of body
Deduplication: keep highest-score chunk per file, max 4 files
"""

from agent.context import RunContext


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
    raise NotImplementedError("retriever.run not yet implemented")
