"""Retrieval metrics for the eval harness.

CRITICAL distinction: the retriever returns *chunks*, gold labels are *files*.
Always map the ranked chunk list to a ranked list of unique file paths first
(preserving the rank of each file's first occurrence), then score against the
gold file set. A silent bug in this mapping quietly invalidates every number
the harness produces, so this module is pure and unit-tested against
hand-constructed ranked lists.

No pandas — numpy is used only for aggregate means.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

K_VALUES = (1, 3, 5, 10)


def chunks_to_ranked_files(chunk_files: Iterable[str]) -> list[str]:
    """Collapse a rank-ordered list of chunk file paths into a rank-ordered
    list of UNIQUE file paths, keeping each file at the rank of its first
    occurrence.

    Example: [a, a, b, a, c] -> [a, b, c]
    """
    seen: set[str] = set()
    ranked: list[str] = []
    for f in chunk_files:
        if f not in seen:
            seen.add(f)
            ranked.append(f)
    return ranked


def recall_at_k(ranked_files: list[str], gold_files: Iterable[str], k: int) -> float:
    """Fraction of gold files present in the top-k retrieved files.

    Returns 0.0 when there are no gold files (an unanswerable row should not
    inflate the average).
    """
    gold = set(gold_files)
    if not gold:
        return 0.0
    topk = set(ranked_files[:k])
    return len(gold & topk) / len(gold)


def hit_at_k(ranked_files: list[str], gold_files: Iterable[str], k: int) -> bool:
    """True if at least one gold file appears in the top-k retrieved files."""
    gold = set(gold_files)
    if not gold:
        return False
    return bool(gold & set(ranked_files[:k]))


def mrr(ranked_files: list[str], gold_files: Iterable[str]) -> float:
    """Reciprocal rank (1-indexed) of the first gold file in the ranking.

    Returns 0.0 if no gold file is retrieved.
    """
    gold = set(gold_files)
    if not gold:
        return 0.0
    for i, f in enumerate(ranked_files, start=1):
        if f in gold:
            return 1.0 / i
    return 0.0


def score_issue(
    chunk_files: Iterable[str],
    gold_files: Iterable[str],
    k_values: Iterable[int] = K_VALUES,
) -> dict:
    """Compute all per-issue metrics from a ranked list of chunk file paths.

    Returns a dict with the mapped ranked files plus recall@k, hit@k, and mrr.
    """
    ranked_files = chunks_to_ranked_files(chunk_files)
    gold = list(gold_files)
    result: dict = {
        "ranked_files": ranked_files,
        "gold_files": gold,
        "mrr": mrr(ranked_files, gold),
    }
    for k in k_values:
        result[f"recall@{k}"] = recall_at_k(ranked_files, gold, k)
        result[f"hit@{k}"] = hit_at_k(ranked_files, gold, k)
    return result


def aggregate(
    per_issue: list[dict],
    k_values: Iterable[int] = K_VALUES,
) -> dict:
    """Aggregate per-issue metric dicts into means.

    recall@k -> mean recall across issues; hit@k -> fraction of issues with a
    hit; mrr -> mean reciprocal rank. Returns zeros for an empty input.
    """
    k_values = list(k_values)
    n = len(per_issue)
    agg: dict = {"n": n}
    if n == 0:
        agg["mrr"] = 0.0
        for k in k_values:
            agg[f"recall@{k}"] = 0.0
            agg[f"hit@{k}"] = 0.0
        return agg

    agg["mrr"] = float(np.mean([row["mrr"] for row in per_issue]))
    for k in k_values:
        agg[f"recall@{k}"] = float(np.mean([row[f"recall@{k}"] for row in per_issue]))
        agg[f"hit@{k}"] = float(np.mean([1.0 if row[f"hit@{k}"] else 0.0 for row in per_issue]))
    return agg
