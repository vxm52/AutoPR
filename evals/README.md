# Retrieval evaluation harness

Measures whether the CrossEncoder reranker actually improves **file** retrieval,
on a labeled benchmark of GitHub issues. Retrieval only — no planner, no code
generation, no LLM calls. Once the dataset exists and repos are cloned, the
harness runs with **no `LLM_API_KEY` and no `GITHUB_TOKEN`**.

## Files

| File | Purpose |
|------|---------|
| `metrics.py` | Pure metrics: chunk→file mapping, recall@k, hit@k, MRR. |
| `run_eval.py` | Runner: clones/indexes per row, runs the config matrix, writes results. |
| `dataset.jsonl` | **Real** hand-labeled issues. You populate this. |
| `fixtures/dataset.jsonl` | **Fixture** rows (test-only). Never merged with real rows. |
| `fixtures/toyrepo/` | Plain source files for the fixtures (no nested `.git`). |

Real and fixture runs are kept strictly separate. `run_eval.py` refuses to run a
dataset that mixes fixture and non-fixture rows, so `results.md` can never
aggregate a toy row into a real benchmark.

**The fixture validates harness mechanics only — it is not a reranker verdict.**
The toy repo is smaller than `candidate_k`, so FAISS returns the whole repo and
the reranker has nothing to prune; the resulting Δ=0.000 in
`results.fixtures.md` is the intended, correct outcome (see
`tests/test_evals_fixture.py`). The reranker's actual effect is measured only on
`dataset.jsonl`.

## Dataset schema (`dataset.jsonl`, one JSON object per line)

```json
{
  "id": "wireflow-12",
  "repo": "vxm52/wireflow",
  "issue_number": 12,
  "title": "…",
  "body": "…",
  "gold_files": ["backend/api.py"],
  "base_sha": "abc1234",
  "source": "pr#14"
}
```

- `gold_files` — repo-relative paths taken from the merged PR that closed the
  issue. Exclude lockfiles/generated files.
- `base_sha` — the commit **immediately before** that PR merged. Index at this
  commit; otherwise the fix is already in the tree and retrieval is trivially
  easy. If `base_sha` is absent/`null` for a **remote** repo, the runner falls
  back to `HEAD` and flags the row as `post-fix state` in the output.

### Fixture rows add two fields

- `"fixture": true` — marks the row as test-only.
- `"local_path"` — repo-relative path to a local source tree (e.g.
  `evals/fixtures/toyrepo`). Fixture rows use `"base_sha": null` and are indexed
  directly from a copy of that path (no clone, no checkout).

## Running

```bash
# Fixture smoke run (offline, deterministic):
python -m evals.run_eval --dataset evals/fixtures/dataset.jsonl

# Real benchmark:
python -m evals.run_eval --dataset evals/dataset.jsonl
```

Output paths are derived from the dataset so a fixture run never overwrites a
real run: `evals/results.<name>.md` and `evals/results.<name>.json` (override
with `--out <base_path>`).

## Config matrix

Default matrix (per row):

- `use_reranker` ∈ `[True, False]` — reranker on vs. raw FAISS ordering.
- `candidate_k` ∈ `[20]` — raw FAISS candidates before reranking.
- `faiss_query_chars` ∈ `[200, None]` — body chars used for the ANN query.
  `200` is the production config; `None` embeds the full body. Reported as its
  own comparison so the harness quantifies the truncation cost instead of
  hiding it.
