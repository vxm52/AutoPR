"""FastAPI application for AutoPR.

Provides /run and /status endpoints for triggering and monitoring
the AutoPR pipeline.
"""

import os
import threading
import uuid

import git
from fastapi import FastAPI, HTTPException
from fastapi.background import BackgroundTasks
from github import Github
from pydantic import BaseModel

from agent.context import Issue, RunContext
from agent.controller import AgentController

app = FastAPI(
    title="AutoPR",
    description="Autonomous developer agent that creates PRs from GitHub issues",
    version="0.1.0",
)

# run_id → state dict
_runs: dict[str, dict] = {}
_runs_lock = threading.Lock()


class RunRequest(BaseModel):
    issue_number: int
    repo: str  # "owner/name"


def _clone_or_pull(owner: str, name: str, token: str) -> str:
    clone_base = os.environ.get("REPO_CLONE_PATH", "/tmp/autopr_repos")
    repo_path = os.path.join(clone_base, f"{owner}_{name}")
    auth_url = f"https://{token}@github.com/{owner}/{name}.git"

    if os.path.exists(repo_path):
        g = git.Repo(repo_path)
        origin = g.remote("origin")
        old_url = origin.url
        try:
            origin.set_url(auth_url)
            origin.pull()
        finally:
            origin.set_url(old_url)
    else:
        os.makedirs(clone_base, exist_ok=True)
        g = git.Repo.clone_from(auth_url, repo_path)
        g.remote("origin").set_url(f"https://github.com/{owner}/{name}.git")

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


def _run_pipeline(run_id: str, issue_number: int, owner: str, name: str) -> None:
    with _runs_lock:
        _runs[run_id]["status"] = "running"

    try:
        token = os.environ.get("GITHUB_TOKEN", "")
        repo_path = _clone_or_pull(owner, name, token)
        issue = _fetch_issue(owner, name, issue_number, token)

        ctx = RunContext(issue=issue, repo_path=repo_path)
        AgentController().run(ctx)

        with _runs_lock:
            _runs[run_id].update(
                {
                    "status": "failed" if ctx.errors else "done",
                    "step_log": ctx.step_log,
                    "errors": ctx.errors,
                    "pr_url": ctx.pr_url,
                }
            )
    except Exception as e:
        with _runs_lock:
            _runs[run_id].update({"status": "failed", "errors": [str(e)]})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/run")
async def run_pipeline(request: RunRequest, background_tasks: BackgroundTasks) -> dict:
    if "/" not in request.repo:
        raise HTTPException(status_code=400, detail="repo must be in owner/name format")

    owner, name = request.repo.split("/", 1)
    run_id = str(uuid.uuid4())

    with _runs_lock:
        _runs[run_id] = {
            "run_id": run_id,
            "status": "pending",
            "step_log": [],
            "errors": [],
            "pr_url": None,
        }

    background_tasks.add_task(_run_pipeline, run_id, request.issue_number, owner, name)
    return {"run_id": run_id, "status": "pending"}


@app.get("/status/{run_id}")
async def get_status(run_id: str) -> dict:
    with _runs_lock:
        run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")
    return run
