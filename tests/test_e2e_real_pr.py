#!/usr/bin/env python3
"""End-to-end pipeline test that creates a real GitHub PR on vxm52/wireflow.

Differences from test_e2e.py:
- Clones vxm52/wireflow so origin is a real remote.
- Monkey-patches MockLLMClient's code_generator branch to append
  "# AutoPR test" to the file, forcing a real diff → real commit → real PR.
- Requires GITHUB_TOKEN to be set in the environment.

Usage:
    GITHUB_TOKEN=<token> venv/bin/python tests/test_e2e_real_pr.py
"""

import os
import shutil
import sys
from pathlib import Path

# Must be set before any agent imports so get_client() returns MockLLMClient.
os.environ["USE_MOCK_LLM"] = "true"

import git

from agent.context import Issue, RunContext
from agent.controller import AgentController

WIREFLOW_PATH = "/tmp/wireflow"
REPO_OWNER = "vxm52"
REPO_NAME = "wireflow"


def _check_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        sys.exit("ERROR: GITHUB_TOKEN is not set. Export it before running this test.")
    return token


def _clone_wireflow(token: str) -> str:
    """Clone vxm52/wireflow into /tmp/wireflow, replacing any existing copy."""
    repo_path = Path(WIREFLOW_PATH)
    if repo_path.exists():
        shutil.rmtree(repo_path)

    clone_url = f"https://{token}@github.com/{REPO_OWNER}/{REPO_NAME}.git"
    print(f"Cloning {REPO_OWNER}/{REPO_NAME} → {WIREFLOW_PATH} …")
    repo = git.Repo.clone_from(clone_url, str(repo_path))
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "AutoPR Test")
        cfg.set_value("user", "email", "test@autopr.local")

    # Ensure the file the mock plan always targets exists on disk.
    # If the repo doesn't have it yet, create it so code_generator can read it.
    target = repo_path / "agent" / "steps" / "issue_parser.py"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            '"""Issue parser stub."""\n'
            "from agent.context import RunContext\n\n\n"
            "def run(ctx: RunContext) -> None:\n"
            '    ctx.issue.task_type = "bug_fix"\n'
        )
        # Stage and commit so pr_creator's diff-against-HEAD works correctly.
        repo.index.add(["agent/steps/issue_parser.py"])
        repo.index.commit("chore: add issue_parser stub")
        # Push the base commit so the PR branch has a common ancestor.
        auth_url = f"https://{token}@github.com/{REPO_OWNER}/{REPO_NAME}.git"
        repo.remote("origin").set_url(auth_url)
        repo.remote("origin").push()
        repo.remote("origin").set_url(
            f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git"
        )

    return str(repo_path)


def _patch_mock_llm() -> None:
    """Replace the code_generator branch of MockLLMClient so it appends a comment.

    Without this, the mock returns unchanged file content, producing an empty
    diff and skipping the commit. With this patch, every generated file gets
    '# AutoPR test' appended, guaranteeing a real diff and a real PR.
    """
    from llm.mock_client import MockLLMClient

    original_complete = MockLLMClient.complete

    def patched_complete(self, system: str, user: str, max_tokens: int = 2000) -> str:
        result = original_complete(self, system, user, max_tokens)
        if "editing a single source file" in system.lower():
            return result.rstrip("\n") + "\n# AutoPR test\n"
        return result

    MockLLMClient.complete = patched_complete


def main() -> None:
    token = _check_token()
    repo_path = _clone_wireflow(token)
    _patch_mock_llm()

    print(f"\nRepo: {repo_path}")

    ctx = RunContext(
        issue=Issue(
            number=2,
            title="Add error handling to main component",
            body="The main component has no error handling. Add a try/catch.",
            repo_owner=REPO_OWNER,
            repo_name=REPO_NAME,
        ),
        repo_path=repo_path,
    )

    AgentController().run(ctx)

    print("\n=== step_log ===")
    for line in ctx.step_log:
        print(line)

    if ctx.errors:
        print("\n=== errors ===")
        for err in ctx.errors:
            print(err)

    print(f"\nctx.pr_url = {ctx.pr_url}")

    failed = any(line.startswith("ERR") for line in ctx.step_log)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
