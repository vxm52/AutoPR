"""Fixture-level invariant test for the eval harness.

This codifies WHY the fixture reranker delta is exactly 0.000, so a future
change to candidate handling breaks a test that explains the invariant instead
of silently changing a mysterious flat result.

The invariant: when candidate_k >= the repo's total chunk count, FAISS returns
the whole repo as candidates, so use_reranker=True and use_reranker=False draw
from the *identical candidate set*. The reranker can only reorder that set, never
add or remove a file — so the set of retrieved files is identical either way, and
no gold file can be gained or lost by toggling the reranker. (Ordered rankings
DO differ: the reranker reorders. Set-equality is the guarantee, not order.)

This is an integration test: it indexes the toy fixture with the real embedding
model. It is skipped if the models are unavailable (e.g. fully offline with no
cache), and skipped if the reranker fails to load — otherwise reranker=on would
fall back to FAISS and the comparison would pass vacuously.
"""

import json
import shutil
from pathlib import Path

import pytest

from agent.context import Issue, RunContext
from agent.steps import repo_indexer
from agent.steps.retriever import FAISS_CANDIDATES, StepError, retrieve, _get_rerank_model
from evals import metrics

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_REPO = REPO_ROOT / "evals" / "fixtures" / "toyrepo"
FIXTURE_DATASET = REPO_ROOT / "evals" / "fixtures" / "dataset.jsonl"
CANDIDATE_K = FAISS_CANDIDATES


@pytest.fixture(scope="module")
def indexed_toyrepo(tmp_path_factory):
    """Copy the toy fixture to a tmp dir and build its FAISS index once."""
    dest = tmp_path_factory.mktemp("toyrepo")
    repo_path = dest / "toyrepo"
    shutil.copytree(FIXTURE_REPO, repo_path)
    ctx = RunContext(
        issue=Issue(number=0, title="", body="", repo_owner="", repo_name=""),
        repo_path=str(repo_path),
    )
    try:
        repo_indexer.run(ctx)
    except StepError as e:  # embedding model unavailable offline
        pytest.skip(f"cannot index fixture (model unavailable): {e}")
    return repo_path


def _chunk_count(repo_path: Path) -> int:
    return len(json.loads((repo_path / ".autopr_index" / "chunks.json").read_text()))


def _load_rows():
    return [json.loads(line) for line in FIXTURE_DATASET.read_text().splitlines() if line.strip()]


def test_full_candidate_window_premise_holds(indexed_toyrepo):
    # The invariant below only applies while the whole repo fits in one window.
    # If the fixture grows past candidate_k, this fails legibly to say so.
    assert _chunk_count(indexed_toyrepo) <= CANDIDATE_K


def test_reranker_toggle_preserves_file_set_and_fixture_metrics(indexed_toyrepo):
    if _get_rerank_model() is None:
        pytest.skip("reranker unavailable — on/off would compare vacuously")

    chunk_count = _chunk_count(indexed_toyrepo)
    assert chunk_count <= CANDIDATE_K, "premise broken: repo larger than candidate window"

    for row in _load_rows():
        on = retrieve(row["title"], row["body"], str(indexed_toyrepo),
                      top_k=CANDIDATE_K, candidate_k=CANDIDATE_K, use_reranker=True)
        off = retrieve(row["title"], row["body"], str(indexed_toyrepo),
                       top_k=CANDIDATE_K, candidate_k=CANDIDATE_K, use_reranker=False)

        # Sanity: the whole repo really was the candidate pool for both.
        assert on.candidate_count == off.candidate_count == chunk_count

        files_on = metrics.chunks_to_ranked_files([c.file for c in on.chunks])
        files_off = metrics.chunks_to_ranked_files([c.file for c in off.chunks])

        # INVARIANT: identical candidate set -> identical retrieved file set.
        assert set(files_on) == set(files_off), (
            f"{row['id']}: reranker changed the file SET, not just order — "
            "the candidate window no longer covers the whole repo?"
        )

        # FIXTURE REGRESSION: on THIS repo the gold files also land at the same
        # ranks either way, so every metric delta is exactly zero. This locks
        # the intentional Δ=0.000 in results.fixtures.md.
        m_on = metrics.score_issue([c.file for c in on.chunks], row["gold_files"])
        m_off = metrics.score_issue([c.file for c in off.chunks], row["gold_files"])
        for key in [f"recall@{k}" for k in metrics.K_VALUES] + \
                   [f"hit@{k}" for k in metrics.K_VALUES] + ["mrr"]:
            assert m_on[key] == m_off[key], (
                f"{row['id']}: reranker moved {key} on the fixture "
                f"({m_off[key]} -> {m_on[key]}); the intentional Δ=0 no longer holds"
            )
