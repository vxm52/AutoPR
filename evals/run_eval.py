"""Retrieval eval runner.

Runs the shared production retrieval path (`agent.steps.retriever.retrieve`)
over a labeled dataset under a config matrix, and reports whether the
CrossEncoder reranker improves *file* retrieval.

No LLM and no GitHub API are needed to run: given a dataset and (for remote
rows) clones, this reads the on-disk FAISS index only. Build/warm the index
once per (repo, sha) before scoring anything.

Usage:
    python -m evals.run_eval --dataset evals/fixtures/dataset.jsonl
    python -m evals.run_eval --dataset evals/dataset.jsonl --out evals/results.custom
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional

# Allow `python evals/run_eval.py` in addition to `python -m evals.run_eval`.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agent.context import Issue, RunContext, StepError
from agent.steps import repo_indexer
from agent.steps.retriever import FAISS_CANDIDATES, retrieve
from evals import metrics

# --- Config matrix ---------------------------------------------------------

# Full cross product: use_reranker × candidate_k × faiss_query_chars.
DEFAULT_MATRIX: list[dict] = [
    {"use_reranker": True, "candidate_k": 20, "faiss_query_chars": 200},
    {"use_reranker": False, "candidate_k": 20, "faiss_query_chars": 200},
    {"use_reranker": True, "candidate_k": 20, "faiss_query_chars": None},
    {"use_reranker": False, "candidate_k": 20, "faiss_query_chars": None},
]

K_VALUES = metrics.K_VALUES


def config_label(cfg: dict) -> str:
    qc = cfg["faiss_query_chars"]
    return (
        f"rerank={'on' if cfg['use_reranker'] else 'off'} "
        f"qchars={qc if qc is not None else 'full'} "
        f"cand={cfg['candidate_k']}"
    )


# --- Dataset loading & validation -----------------------------------------

def load_dataset(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path) as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{i}: invalid JSON — {e}")
    return rows


def is_fixture(row: dict) -> bool:
    return bool(row.get("fixture"))


def validate_homogeneous(rows: list[dict], path: str) -> bool:
    """Return True if this is a fixture run. Fail loudly on any mix of fixture
    and real rows so results can never aggregate across the two."""
    if not rows:
        raise SystemExit(f"{path}: dataset is empty — nothing to evaluate.")

    kinds = {is_fixture(r) for r in rows}
    if len(kinds) > 1:
        fixture_ids = [r.get("id") for r in rows if is_fixture(r)]
        real_ids = [r.get("id") for r in rows if not is_fixture(r)]
        raise SystemExit(
            "Refusing to run: dataset mixes fixture and real rows.\n"
            f"  fixture rows: {fixture_ids}\n"
            f"  real rows:    {real_ids}\n"
            "Fixture rows (test-only) must never be scored alongside real rows."
        )

    fixture_run = kinds == {True}
    # Per-row shape checks catch a mislabeled row before it distorts numbers.
    for r in rows:
        if not r.get("gold_files"):
            raise SystemExit(f"row {r.get('id')!r}: missing gold_files.")
        if is_fixture(r):
            if not r.get("local_path"):
                raise SystemExit(f"fixture row {r.get('id')!r}: missing local_path.")
            if r.get("base_sha") is not None:
                raise SystemExit(
                    f"fixture row {r.get('id')!r}: base_sha must be null (indexed from local_path)."
                )
        else:
            if "/" not in str(r.get("repo", "")):
                raise SystemExit(
                    f"real row {r.get('id')!r}: repo must be 'owner/name'."
                )
    return fixture_run


# --- Repo preparation (clone/copy + checkout) ------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")


def _clone_root() -> Path:
    root = Path(os.getenv("REPO_CLONE_PATH", "/tmp/autopr_repos"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def prepare_fixture(row: dict) -> tuple[str, bool]:
    """Copy a fixture's local_path into a throwaway work dir. Returns
    (repo_path, post_fix=False). Deterministic: fresh copy each run."""
    src = Path(_REPO_ROOT) / row["local_path"]
    if not src.is_dir():
        raise SystemExit(f"fixture row {row.get('id')!r}: local_path not found: {src}")
    dest = _clone_root() / f"fixture-{_slug(row['local_path'])}"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return str(dest), False


def prepare_remote(row: dict) -> tuple[str, bool]:
    """Clone owner/repo and check out base_sha (or HEAD, flagged post-fix).
    Returns (repo_path, post_fix)."""
    import git  # GitPython — only needed for remote rows

    owner_name = row["repo"]
    base_sha = row.get("base_sha")
    post_fix = base_sha is None
    key = _slug(owner_name) + ("@" + str(base_sha)[:12] if base_sha else "@HEAD")
    dest = _clone_root() / key

    url = f"https://github.com/{owner_name}.git"
    if (dest / ".git").exists():
        repo = git.Repo(str(dest))
        try:
            repo.remotes.origin.fetch()
        except Exception:
            pass
    else:
        if dest.exists():
            shutil.rmtree(dest)
        repo = git.Repo.clone_from(url, str(dest))

    if base_sha is not None:
        repo.git.checkout(base_sha)
    return str(dest), post_fix


def prepare_repo(row: dict) -> tuple[str, bool]:
    return prepare_fixture(row) if is_fixture(row) else prepare_remote(row)


def warm_index(repo_path: str) -> None:
    """Build/refresh the FAISS index for a repo exactly once, before timing."""
    ctx = RunContext(
        issue=Issue(number=0, title="", body="", repo_owner="", repo_name=""),
        repo_path=repo_path,
    )
    try:
        repo_indexer.run(ctx)
    except StepError as e:
        raise SystemExit(f"indexing failed for {repo_path}: {e}")


# --- Scoring ---------------------------------------------------------------

def score_row(row: dict, repo_path: str, cfg: dict, post_fix: bool) -> dict:
    # top_k = candidate_k so the full ranking is available; recall@k slices it.
    result = retrieve(
        row["title"],
        row["body"],
        repo_path,
        top_k=cfg["candidate_k"],
        candidate_k=cfg["candidate_k"],
        use_reranker=cfg["use_reranker"],
        faiss_query_chars=cfg["faiss_query_chars"],
    )
    chunk_files = [c.file for c in result.chunks]
    scored = metrics.score_issue(chunk_files, row["gold_files"], K_VALUES)
    scored["id"] = row["id"]
    scored["reranker_failed"] = bool(result.reranker_failed and cfg["use_reranker"])
    scored["candidate_count"] = result.candidate_count
    scored["post_fix"] = post_fix
    return scored


def run_matrix(rows: list[dict], matrix: list[dict]) -> dict:
    # Prepare + warm each unique target once, then score every row/config.
    prepared: dict[str, tuple[str, bool]] = {}  # target key -> (repo_path, post_fix)
    row_target: dict[str, str] = {}
    for row in rows:
        if is_fixture(row):
            key = "fixture:" + row["local_path"]
        else:
            key = f"{row['repo']}@{row.get('base_sha') or 'HEAD'}"
        row_target[row["id"]] = key
        if key not in prepared:
            repo_path, post_fix = prepare_repo(row)
            warm_index(repo_path)
            prepared[key] = (repo_path, post_fix)

    configs: dict[str, dict] = {}
    for cfg in matrix:
        label = config_label(cfg)
        per_issue = []
        for row in rows:
            repo_path, post_fix = prepared[row_target[row["id"]]]
            per_issue.append(score_row(row, repo_path, cfg, post_fix))
        configs[label] = {
            "config": cfg,
            "aggregate": metrics.aggregate(per_issue, K_VALUES),
            "per_issue": per_issue,
        }
    return configs


# --- Reporting -------------------------------------------------------------

def _fmt(x: float) -> str:
    return f"{x:.3f}"


def _first_gold_rank(row: dict) -> str:
    """1-indexed rank of the first gold file, or '—' if not retrieved."""
    gold = set(row["gold_files"])
    for i, f in enumerate(row["ranked_files"], start=1):
        if f in gold:
            return str(i)
    return "—"


def build_results_md(dataset_path: str, name: str, fixture_run: bool, configs: dict, rows: list[dict]) -> str:
    n = len(rows)
    lines: list[str] = []
    lines.append(f"# Retrieval eval — `{name}`")
    lines.append("")
    lines.append(f"- Dataset: `{dataset_path}`")
    lines.append(f"- Rows (n): **{n}**")
    lines.append(f"- Run type: **{'FIXTURE (test-only)' if fixture_run else 'real'}**")
    lines.append("")

    # Reranker-fallback warning: if any reranker config fell back to FAISS, the
    # reranker vs. no-reranker comparison is measuring the same thing.
    fell_back = {
        label
        for label, data in configs.items()
        if data["config"]["use_reranker"]
        and any(r["reranker_failed"] for r in data["per_issue"])
    }
    if fell_back:
        lines.append("> ⚠️ **Reranker unavailable** for some rows — those "
                     "`rerank=on` configs fell back to FAISS ordering, so the "
                     "reranker comparison below is NOT valid for this run.")
        lines.append("")

    post_fix_ids = sorted({r["id"] for d in configs.values() for r in d["per_issue"] if r["post_fix"]})
    if post_fix_ids:
        lines.append(f"> ⚠️ **Post-fix state** (no `base_sha`, indexed at HEAD): "
                     f"{', '.join('`'+i+'`' for i in post_fix_ids)} — retrieval on "
                     "these rows is optimistic.")
        lines.append("")

    # Aggregate table.
    lines.append("## Aggregate")
    lines.append("")
    header = ["config", "n"]
    for k in K_VALUES:
        header.append(f"recall@{k}")
    for k in K_VALUES:
        header.append(f"hit@{k}")
    header.append("MRR")
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for label, data in configs.items():
        agg = data["aggregate"]
        cells = [label, str(agg["n"])]
        cells += [_fmt(agg[f"recall@{k}"]) for k in K_VALUES]
        cells += [_fmt(agg[f"hit@{k}"]) for k in K_VALUES]
        cells.append(_fmt(agg["mrr"]))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # Focused comparisons.
    lines.append("## Comparisons")
    lines.append("")
    lines.append("### Reranker effect (production ANN query, `qchars=200`)")
    lines.append("")
    lines += _comparison_block(
        configs,
        a="rerank=on qchars=200 cand=20",
        b="rerank=off qchars=200 cand=20",
        a_name="reranker",
        b_name="raw FAISS",
    )
    lines.append("")
    lines.append("### Truncation cost (reranker on): `qchars=200` vs full body")
    lines.append("")
    lines += _comparison_block(
        configs,
        a="rerank=on qchars=200 cand=20",
        b="rerank=on qchars=full cand=20",
        a_name="qchars=200 (prod)",
        b_name="qchars=full",
    )
    lines.append("")

    # Per-issue breakdown (one block per config).
    lines.append("## Per-issue breakdown")
    lines.append("")
    for label, data in configs.items():
        lines.append(f"### `{label}`")
        lines.append("")
        cols = ["id", "gold_files", "first-gold rank", "recall@5", "hit@5", "MRR", "flags"]
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join(["---"] * len(cols)) + "|")
        for r in data["per_issue"]:
            flags = []
            if r["post_fix"]:
                flags.append("post-fix")
            if r["reranker_failed"]:
                flags.append("rerank-fallback")
            lines.append("| " + " | ".join([
                f"`{r['id']}`",
                ", ".join(f"`{g}`" for g in r["gold_files"]),
                _first_gold_rank(r),
                _fmt(r["recall@5"]),
                _fmt(1.0 if r["hit@5"] else 0.0),
                _fmt(r["mrr"]),
                ", ".join(flags) or "—",
            ]) + " |")
        lines.append("")

    return "\n".join(lines)


def _comparison_block(configs: dict, a: str, b: str, a_name: str, b_name: str) -> list[str]:
    if a not in configs or b not in configs:
        return ["_(configs not present in this matrix)_"]
    aa, ba = configs[a]["aggregate"], configs[b]["aggregate"]
    out = ["| metric | " + f"{a_name} | {b_name} | Δ (a−b) |", "|---|---|---|---|"]
    for metric in ["recall@1", "recall@5", "hit@5", "mrr"]:
        delta = aa[metric] - ba[metric]
        out.append(f"| {metric} | {_fmt(aa[metric])} | {_fmt(ba[metric])} | {delta:+.3f} |")
    return out


# --- Main ------------------------------------------------------------------

def derive_name(dataset_path: str) -> str:
    p = Path(dataset_path)
    stem = p.stem
    # Generic filenames (dataset.jsonl) collide between fixtures/ and evals/;
    # fall back to the parent directory name so outputs never overwrite.
    if stem in ("dataset", "data"):
        return _slug(p.parent.name)
    return _slug(stem)


def main() -> None:
    ap = argparse.ArgumentParser(description="Retrieval eval runner")
    ap.add_argument("--dataset", required=True, help="Path to a .jsonl dataset")
    ap.add_argument("--out", default=None,
                    help="Output base path (writes <out>.md and <out>.json). "
                         "Defaults to evals/results.<name>.")
    args = ap.parse_args()

    rows = load_dataset(args.dataset)
    fixture_run = validate_homogeneous(rows, args.dataset)

    name = derive_name(args.dataset)
    out_base = args.out or str(Path(_REPO_ROOT) / "evals" / f"results.{name}")

    configs = run_matrix(rows, DEFAULT_MATRIX)

    results = {
        "dataset": name,
        "dataset_path": args.dataset,
        "fixture_run": fixture_run,
        "matrix": DEFAULT_MATRIX,
        "configs": configs,
    }

    md = build_results_md(args.dataset, name, fixture_run, configs, rows)

    Path(out_base + ".json").write_text(json.dumps(results, indent=2, default=str))
    Path(out_base + ".md").write_text(md)

    print(md)
    print(f"\nWrote {out_base}.md and {out_base}.json")


if __name__ == "__main__":
    main()
