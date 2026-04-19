# AutoPR

An autonomous developer agent that turns a GitHub issue into a pull request. Point it at a repo and an issue number — it reads the codebase, makes a plan, writes the code, and opens a PR.

---

## How it works

AutoPR runs a seven-step pipeline. Each step is a discrete module; a shared `RunContext` object carries state between them.

| # | Step | What it does |
|---|------|-------------|
| 1 | **Issue Parser** | Classifies the issue as `bug_fix`, `feature`, or `refactor` via LLM |
| 2 | **Repo Indexer** | Chunks the codebase by function/class boundary and builds a FAISS semantic index |
| 3 | **Retriever** | Embeds the issue and retrieves the top-4 most relevant files by cosine similarity |
| 4 | **Planner** | Asks the LLM to produce a structured JSON change plan (files to modify, reasoning, confidence) |
| 5 | **Code Generator** | For each file in the plan, sends a separate LLM call and receives the complete modified file |
| 6 | **Diff Generator** | Computes unified diffs with `difflib` and validates each one with `patch --dry-run` |
| 7 | **PR Creator** | Creates a branch, commits the changes, pushes, and opens a pull request via the GitHub API |

---

## Architecture
```
autopr/
├── agent/
│   ├── controller.py       # Sequential step runner (AgentController)
│   ├── context.py          # RunContext dataclass — shared state across all steps
│   └── steps/
│       ├── issue_parser.py
│       ├── repo_indexer.py
│       ├── retriever.py
│       ├── planner.py
│       ├── code_generator.py
│       ├── diff_generator.py
│       └── pr_creator.py
├── api/
│   └── main.py             # FastAPI app — /run and /status endpoints
├── llm/
│   ├── client.py           # OpenAI-compatible LLM wrapper
│   └── mock_client.py      # Deterministic mock for local testing
├── github_client/
│   └── client.py           # PyGitHub wrapper
├── frontend/               # React + Vite UI
└── tests/
├── test_e2e.py         # End-to-end test with USE_MOCK_LLM=true
└── test_e2e_real_pr.py # Full PR creation test against a real GitHub repo
```

The API runs pipeline steps one-by-one and pushes `step_log` updates after each step, so the frontend can stream live progress without websockets.

---

## Prerequisites

- Python 3.10+
- Node 18+ (for the frontend)
- A GitHub personal access token with `repo` scope and `Contents` + `Pull requests` write permissions
- A course-provided or OpenAI-compatible LLM endpoint

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

Create a `.env` file in the project root with the following variables:

```bash
# GitHub — personal access token with repo scope (Contents + Pull requests write)
GITHUB_TOKEN=ghp_...

# LLM — OpenAI-compatible endpoint
LLM_API_KEY=...
LLM_BASE_URL=...        # e.g. https://api.openai.com/v1
LLM_MODEL=gpt-4o        # optional — set if the API requires a model name

# Local clone cache
REPO_CLONE_PATH=/tmp/autopr_repos

# Set to true to run the full pipeline without real LLM calls (for development/testing)
USE_MOCK_LLM=false
```

**3. Install frontend dependencies**

```bash
cd frontend
npm install
```

---

## Running

**API server**

```bash
source venv/bin/activate
set -a; source .env; set +a
uvicorn api.main:app --reload
```

The API listens on `http://localhost:8000`.

**Frontend**

```bash
cd frontend
npm run dev
```

The UI runs on `http://localhost:5173`. Vite proxies `/run` and `/status` to the API automatically — no CORS setup needed.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/run` | Start a pipeline run |
| `GET` | `/status/{run_id}` | Poll run state |

**Start a run**

```bash
curl -X POST http://localhost:8000/run \
  -H 'Content-Type: application/json' \
  -d '{"repo": "owner/repo-name", "issue_number": 42}'
```

```json
{ "run_id": "a1b2c3d4-...", "status": "pending" }
```

**Poll status**

```bash
curl http://localhost:8000/status/a1b2c3d4-...
```

```json
{
  "run_id": "a1b2c3d4-...",
  "status": "done",
  "step_log": ["OK  agent.steps.issue_parser", "OK  agent.steps.repo_indexer", "..."],
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

Clones a real repo, forces a real diff via mock patch, and creates an actual PR on GitHub. Verify the PR appears at `https://github.com/vxm52/wireflow/pulls` then close and delete the branch after testing.

---

## UI features

- **Pipeline visualizer** — live node graph showing each step's state (idle / active / ok / warn / err) with connecting lines that fill as steps complete
- **Issue preview** — fetches the GitHub issue from the public API and shows title, body, and labels before you submit
- **Diff viewer** — syntax-highlighted unified diff for every file the agent changed
- **Live step log** — monospace terminal feed; each entry slides in as it arrives
- **Progress bar** — top-of-page bar that fills step-by-step while the pipeline runs

---

## Design decisions

**One LLM call per file.** The code generator never batches multiple files into a single prompt. Each call gets: system prompt + the current file + the change instruction. Tight context = fewer hallucinations.

**Diffs are computed by `difflib`, not the LLM.** The LLM returns the complete modified file; diffing is deterministic and happens in `diff_generator`.

**FAISS index is cached.** `repo_indexer` skips re-embedding if the index already exists and files are unchanged.

**Low-confidence plans fail fast.** If the planner sets `"confidence": "low"` or returns malformed JSON, `StepError` is raised immediately rather than proceeding with a bad plan.

**Branch names are unique per issue.** Format: `autopr/issue-{number}`. If that branch already exists, AutoPR appends `-retry-{n}`.

**Mock LLM for development.** Setting `USE_MOCK_LLM=true` routes all LLM calls to `MockLLMClient`, which returns deterministic hardcoded responses keyed on system prompt keywords. This lets you build and test the full pipeline without API credentials. Set `USE_MOCK_LLM=false` and supply real credentials only when you're ready for a live run.

---

## License

MIT