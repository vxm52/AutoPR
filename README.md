# AutoPR

An autonomous developer agent that turns a GitHub issue into a pull request. Point it at a repo and an issue number — it reads the codebase, makes a plan, writes the code, and opens a PR.

---

## How it works

AutoPR runs a seven-step pipeline. Each step is a discrete module; a shared `RunContext` object carries state between them.

| # | Step | What it does |
|---|------|-------------|
| 1 | **Issue Parser** | Classifies the issue as `bug_fix`, `feature`, or `refactor` via LLM |
| 2 | **Repo Indexer** | Chunks the codebase by function/class boundary and builds a FAISS semantic index |
| 3 | **Retriever** | Embeds the issue, fetches 20 FAISS candidates, reranks them with a CrossEncoder, returns top-5 |
| 4 | **Planner** | Asks the LLM to produce a structured JSON change plan (files to modify, reasoning, confidence) |
| 5 | **Code Generator** | For each file in the plan, sends a separate LLM call and receives the complete modified file |
| 6 | **Diff Generator** | Computes unified diffs with `difflib` and validates each one with `patch --dry-run` |
| 7 | **PR Creator** | Creates a branch, commits the changes, pushes, and opens a pull request via the GitHub API |

---

## Architecture
```
autopr/
├── agent/
│   ├── controller.py         # Sequential step runner
│   ├── context.py            # RunContext dataclass — shared state across all steps
│   └── steps/
│       ├── issue_parser.py
│       ├── repo_indexer.py
│       ├── retriever.py      # FAISS + CrossEncoder reranker
│       ├── planner.py
│       ├── code_generator.py
│       ├── diff_generator.py
│       └── pr_creator.py
├── api/
│   └── main.py               # FastAPI app — /run and /status endpoints
├── llm/
│   ├── client.py             # OpenAI-compatible LLM wrapper with retry logic
│   └── mock_client.py        # Deterministic mock for local testing
├── github_client/
│   └── client.py             # PyGitHub wrapper
├── frontend/                 # React + Vite UI
└── tests/
    ├── test_e2e.py           # End-to-end test with USE_MOCK_LLM=true
    └── test_e2e_real_pr.py   # Full PR creation test against a real GitHub repo
```

The API runs pipeline steps one-by-one and pushes `step_log` updates after each step, so the frontend can stream live progress without websockets.

---

## Prerequisites

- Python 3.10+
- Node 18+ (for the frontend)
- A GitHub personal access token with `repo` scope (Contents, Pull requests, and Issues write)
- A Groq API key — free at [console.groq.com](https://console.groq.com), no credit card required

---

## Setup

**1. Clone and install**

```bash
git clone https://github.com/vxm52/autoPR
cd autoPR
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

**2. Configure environment**

```bash
cp .env.example .env
```

Fill in your `.env`:

```bash
# GitHub — personal access token with repo scope
GITHUB_TOKEN=ghp_...

# LLM — Groq is recommended (free, fast, no credit card)
# Sign up at console.groq.com and create an API key
LLM_API_KEY=gsk_...
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile

# API authentication — all /run requests require this header (X-API-Key)
# If not set, a key is auto-generated and printed to stdout at startup
AUTOPR_API_KEY=your-secret-key

# Rate limiting (default: 5 requests per minute per IP)
RATE_LIMIT=5/minute

# Retrieval — number of reranked chunks sent to the planner
RETRIEVER_TOP_K=5

# Local clone cache
REPO_CLONE_PATH=/tmp/autopr_repos

# Set to true to run without real LLM calls (for development/testing)
USE_MOCK_LLM=false
```

**3. Install frontend dependencies**

```bash
cd frontend && npm install
```

---

## Running

**API server**

```bash
source venv/bin/activate
uvicorn api.main:app --reload
```

The API listens on `http://localhost:8000`.

> **Note:** On first run, the retriever downloads the CrossEncoder reranking model (~80MB). This is a one-time download — subsequent runs use the cached model.

**Frontend**

```bash
cd frontend && npm run dev
```

The UI runs on `http://localhost:5173`.

> **Note:** The issue preview in the UI fetches from GitHub's public API. The target repo must be public for the preview to load.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/run` | Start a pipeline run |
| `GET` | `/status/{run_id}` | Poll run state |

All `/run` requests require the `X-API-Key` header.

**Start a run**

```bash
curl -X POST http://localhost:8000/run \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your-secret-key' \
  -d '{"repo": "owner/repo-name", "issue_number": 42}'
```

```json
{ "run_id": "a1b2c3d4-...", "status": "pending" }
```

**Poll status**

```bash
curl http://localhost:8000/status/a1b2c3d4-... \
  -H 'X-API-Key: your-secret-key'
```

```json
{
  "run_id": "a1b2c3d4-...",
  "status": "done",
  "step_log": ["OK  agent.steps.issue_parser", "..."],
  "errors": [],
  "pr_url": "https://github.com/owner/repo-name/pull/7",
  "diffs": ["--- a/src/foo.py\n+++ b/src/foo.py\n..."]
}
```

`status` is one of `pending` → `running` → `done` | `failed`.

---

## Testing

**Mock LLM test (no credentials needed)**

```bash
USE_MOCK_LLM=true python tests/test_e2e.py
```

Runs the full pipeline with the mock LLM against `/tmp/wireflow`. No API keys or GitHub token required.

**Real PR test (requires GITHUB_TOKEN)**

```bash
GITHUB_TOKEN=your_token python tests/test_e2e_real_pr.py
```

Clones a real repo, forces a real diff, and creates an actual PR on GitHub. Close and delete the branch after testing.

---

## UI features

- **Pipeline visualizer** — live node graph showing each step's state (idle / active / ok / warn / err)
- **Issue preview** — fetches the GitHub issue and shows title, body, and status before you submit
- **Live step log** — monospace terminal feed with each entry arriving in real time
- **Diff viewer** — syntax-highlighted unified diff for every file the agent changed
- **Animated mock panel** — right-column hero animation showing each pipeline step with a unique visual

---

## Design decisions

**One LLM call per file.** The code generator never batches multiple files into a single prompt. Each call gets: system prompt + the current file + the change instruction. Tight context produces more reliable output.

**Diffs are computed by `difflib`, not the LLM.** The LLM returns the complete modified file; diffing is deterministic and happens in `diff_generator`.

**Two-stage retrieval.** The retriever uses FAISS for fast approximate search over the full codebase (top-20 candidates), then a CrossEncoder reranker for precision scoring against the full issue text. This produces better results than embedding similarity alone, especially for ambiguous issues.

**FAISS index is cached.** `repo_indexer` skips re-embedding if the index already exists and files are unchanged.

**Low-confidence plans log a warning and continue.** If the planner returns `"confidence": "low"`, AutoPR logs a warning to `step_log` and proceeds rather than failing hard. If the plan returns malformed JSON, `StepError` is raised immediately.

**LLM calls retry on transient failures.** The client retries up to 3 times with exponential backoff (1s, 2s) on network errors and HTTP 429/5xx responses.

**Branch names are unique per issue.** Format: `autopr/issue-{number}`. If that branch already exists, AutoPR appends `-retry-{n}`.

**Mock LLM for development.** `USE_MOCK_LLM=true` routes all LLM calls to `MockLLMClient`, which returns deterministic responses. Build and test the full pipeline — including real git branches and GitHub PRs — without API credentials.

---

## License

MIT