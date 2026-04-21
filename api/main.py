"""FastAPI application for AutoPR."""

import os
import re
import threading
import time
import uuid

import git
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.background import BackgroundTasks
from fastapi.security.api_key import APIKeyHeader
from github import Github
from pydantic import BaseModel

from agent.context import Issue, RunContext, StepError
from agent.controller import PIPELINE

load_dotenv()

app = FastAPI(
    title="AutoPR",
    description="Autonomous developer agent that creates PRs from GitHub issues",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_API_KEY = os.environ.get("AUTOPR_API_KEY", "")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")

_runs: dict[str, dict] = {}
_runs_lock = threading.Lock()
_RUNS_MAX = 500
_RUNS_TTL = 3600  # seconds


def _require_api_key(key: str | None = Security(_api_key_header)) -> None:
    if _API_KEY and key != _API_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def _evict_old_runs() -> None:
    """Drop settled runs older than TTL, and hard-cap total count."""
    now = time.time()
    with _runs_lock:
        to_delete = [
            rid for rid, r in _runs.items()
            if r["status"] in ("done", "failed") and now - r.get("_created", now) > _RUNS_TTL
        ]
        for rid in to_delete:
            del _runs[rid]
        if len(_runs) >= _RUNS_MAX:
            oldest = sorted(_runs, key=lambda r: _runs[r].get("_created", 0))
            for rid in oldest[:len(_runs) - _RUNS_MAX + 1]:
                del _runs[rid]


class RunRequest(BaseModel):
    issue_number: int
    repo: str  # "owner/name"


def _clone_or_pull(owner: str, name: str, token: str) -> str:
    clone_base = os.environ.get("REPO_CLONE_PATH", "/tmp/autopr_repos")
    repo_path = os.path.join(clone_base, f"{owner}_{name}")
    plain_url = f"https://github.com/{owner}/{name}.git"
    auth_url = f"https://{token}@github.com/{owner}/{name}.git"

    if os.path.exists(repo_path):
        g = git.Repo(repo_path)
        origin = g.remote("origin")
        original_url = origin.url
        try:
            origin.set_url(auth_url)
            default = g.git.symbolic_ref("refs/remotes/origin/HEAD").split("/")[-1]
            g.git.checkout(default)
            origin.pull()
        except Exception as e:
            safe_msg = str(e).replace(token, "<token>") if token else str(e)
            raise RuntimeError(f"git pull failed for {owner}/{name}: {safe_msg}") from None
        finally:
            origin.set_url(original_url)
    else:
        os.makedirs(clone_base, exist_ok=True)
        g = git.Repo.clone_from(auth_url, repo_path)
        g.remote("origin").set_url(plain_url)

    return repo_path


def _fetch_issue(owner: str, name: str, number: int, token: str) -> Issue:
    gh = Github(token)
    gh_issue = gh.get_repo(f"{owner}/{name}").get_issue(number)
    return Issue(
        number=number,
        title=gh_issue.title,
        body=gh_issue.body or "",
        repo_owner=owner,
        repo_name=name,
    )


def _push_step_log(run_id: str, ctx: RunContext) -> None:
    with _runs_lock:
        _runs[run_id]["step_log"] = list(ctx.step_log)


def _run_pipeline(run_id: str, issue_number: int, owner: str, name: str) -> None:
    with _runs_lock:
        _runs[run_id]["status"] = "running"

    try:
        token = os.environ.get("GITHUB_TOKEN", "")
        repo_path = _clone_or_pull(owner, name, token)
        issue = _fetch_issue(owner, name, issue_number, token)
        ctx = RunContext(issue=issue, repo_path=repo_path)

        # Run steps one-by-one so the frontend sees live step_log updates.
        for step_fn in PIPELINE:
            try:
                step_fn(ctx)
                ctx.step_log.append(f"OK  {step_fn.__module__}")
            except StepError as e:
                ctx.errors.append(str(e))
                ctx.step_log.append(f"ERR {step_fn.__module__}: {e}")
                _push_step_log(run_id, ctx)
                break
            finally:
                _push_step_log(run_id, ctx)

        with _runs_lock:
            _runs[run_id].update({
                "status": "failed" if ctx.errors else "done",
                "step_log": ctx.step_log,
                "errors": ctx.errors,
                "pr_url": ctx.pr_url,
                "diffs": ctx.diffs,
            })
    except Exception as e:
        with _runs_lock:
            _runs[run_id].update({"status": "failed", "errors": [str(e)]})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/run")
async def run_pipeline(
    request: RunRequest,
    background_tasks: BackgroundTasks,
    _: None = Security(_require_api_key),
) -> dict:
    if "/" not in request.repo:
        raise HTTPException(status_code=400, detail="repo must be in owner/name format")

    owner, name = request.repo.split("/", 1)
    if not _SAFE_NAME_RE.match(owner) or not _SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="owner and repo name must be alphanumeric (letters, digits, _ . -)")

    _evict_old_runs()
    run_id = str(uuid.uuid4())

    with _runs_lock:
        _runs[run_id] = {
            "run_id": run_id,
            "status": "pending",
            "step_log": [],
            "errors": [],
            "pr_url": None,
            "diffs": [],
            "_created": time.time(),
        }

    background_tasks.add_task(_run_pipeline, run_id, request.issue_number, owner, name)
    return {"run_id": run_id, "status": "pending"}


@app.get("/status/{run_id}")
async def get_status(run_id: str) -> dict:
    with _runs_lock:
        run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")
    return {k: v for k, v in run.items() if not k.startswith("_")}
