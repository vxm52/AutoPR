"""Unit tests for evals/metrics.py.

These use hand-constructed ranked lists (no models, no repos). A silent bug in
this module quietly invalidates every number the harness produces, so the cases
target the failure modes that matter: chunk→file collapsing, rank ordering, and
the recall/hit divergence on multi-file issues.
"""

from evals import metrics


# --- chunks_to_ranked_files -------------------------------------------------

def test_chunk_to_file_dedup_preserves_first_occurrence():
    chunks = ["a.py", "a.py", "b.py", "a.py", "c.py", "b.py"]
    assert metrics.chunks_to_ranked_files(chunks) == ["a.py", "b.py", "c.py"]


def test_chunk_to_file_rank_is_first_not_last():
    # b.py first appears at rank 2 (as a file); its later chunks must not move it.
    chunks = ["a.py", "b.py", "c.py", "c.py", "b.py"]
    ranked = metrics.chunks_to_ranked_files(chunks)
    assert ranked.index("b.py") == 1


def test_empty_chunks():
    assert metrics.chunks_to_ranked_files([]) == []


# --- recall@k ---------------------------------------------------------------

def test_recall_single_gold_in_topk():
    ranked = ["a.py", "b.py", "c.py"]
    assert metrics.recall_at_k(ranked, ["b.py"], 3) == 1.0
    assert metrics.recall_at_k(ranked, ["b.py"], 1) == 0.0


def test_recall_multifile_is_fraction():
    ranked = ["a.py", "b.py", "c.py", "d.py"]
    gold = ["a.py", "d.py"]
    assert metrics.recall_at_k(ranked, gold, 1) == 0.5   # only a.py in top-1
    assert metrics.recall_at_k(ranked, gold, 4) == 1.0   # both in top-4


def test_recall_no_gold_returns_zero():
    assert metrics.recall_at_k(["a.py"], [], 5) == 0.0


# --- hit@k ------------------------------------------------------------------

def test_hit_true_when_any_gold_present():
    ranked = ["a.py", "b.py", "c.py"]
    assert metrics.hit_at_k(ranked, ["b.py", "z.py"], 3) is True
    assert metrics.hit_at_k(ranked, ["z.py"], 3) is False


def test_hit_respects_k_boundary():
    ranked = ["a.py", "b.py", "c.py"]
    assert metrics.hit_at_k(ranked, ["c.py"], 2) is False
    assert metrics.hit_at_k(ranked, ["c.py"], 3) is True


# --- MRR --------------------------------------------------------------------

def test_mrr_reciprocal_rank():
    ranked = ["a.py", "b.py", "c.py"]
    assert metrics.mrr(ranked, ["a.py"]) == 1.0
    assert metrics.mrr(ranked, ["b.py"]) == 0.5
    assert metrics.mrr(ranked, ["c.py"]) == 1.0 / 3


def test_mrr_uses_first_gold():
    ranked = ["a.py", "b.py", "c.py"]
    # Both b and c are gold; first hit is b at rank 2.
    assert metrics.mrr(ranked, ["c.py", "b.py"]) == 0.5


def test_mrr_zero_when_absent():
    assert metrics.mrr(["a.py", "b.py"], ["z.py"]) == 0.0


# --- Adversarial rank ordering (distractor shares vocabulary) ---------------

def test_distractor_ranked_above_gold_penalizes_top1_not_top3():
    # utils.py (wrong, shares vocabulary) is ranked above auth.py (gold).
    ranked = ["utils.py", "auth.py", "api.py"]
    gold = ["auth.py"]
    assert metrics.recall_at_k(ranked, gold, 1) == 0.0   # distractor wins top-1
    assert metrics.recall_at_k(ranked, gold, 3) == 1.0
    assert metrics.mrr(ranked, gold) == 0.5              # gold at rank 2


def test_correct_ordering_beats_distractor_ordering_on_mrr():
    gold = ["auth.py"]
    good = metrics.mrr(["auth.py", "utils.py"], gold)
    bad = metrics.mrr(["utils.py", "auth.py"], gold)
    assert good > bad


# --- score_issue (chunks -> files -> metrics) -------------------------------

def test_score_issue_maps_chunks_to_files():
    # Two chunks from auth.py appear first; gold is the file, not the chunk.
    chunk_files = ["auth.py", "auth.py", "utils.py"]
    scored = metrics.score_issue(chunk_files, ["auth.py"])
    assert scored["ranked_files"] == ["auth.py", "utils.py"]
    assert scored["recall@1"] == 1.0
    assert scored["hit@1"] is True
    assert scored["mrr"] == 1.0


# --- aggregate --------------------------------------------------------------

def test_aggregate_hit_is_fraction_recall_is_mean():
    # Issue 1: single gold, fully hit. Issue 2: two gold, only one in top-3.
    i1 = metrics.score_issue(["a.py", "b.py"], ["a.py"])
    i2 = metrics.score_issue(["c.py", "d.py", "e.py"], ["c.py", "z.py"])
    agg = metrics.aggregate([i1, i2])
    assert agg["n"] == 2
    # hit@3: both issues have at least one gold in top-3 -> 1.0
    assert agg["hit@3"] == 1.0
    # recall@3: issue1 = 1.0, issue2 = 0.5 (only c.py of {c,z}) -> mean 0.75
    assert agg["recall@3"] == 0.75


def test_aggregate_empty():
    agg = metrics.aggregate([])
    assert agg["n"] == 0
    assert agg["mrr"] == 0.0
    assert agg["recall@5"] == 0.0
    assert agg["hit@5"] == 0.0
