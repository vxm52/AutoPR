#!/usr/bin/env python3
"""End-to-end pipeline test: issue_parser through pr_creator, USE_MOCK_LLM=true.

Wires the full AgentController against a synthetic /tmp/wireflow git repo.
Does not require GITHUB_TOKEN or a real LLM endpoint.

Usage:
    USE_MOCK_LLM=true python tests/test_e2e.py
    # or just:
    python tests/test_e2e.py  (USE_MOCK_LLM is set programmatically below)
"""

import os
import shutil
import sys
from pathlib import Path

# Must be set before importing any agent modules so get_client() picks up MockLLMClient.
os.environ["USE_MOCK_LLM"] = "true"

import git  # GitPython

from agent.context import Issue, RunContext
from agent.controller import AgentController

WIREFLOW_PATH = "/tmp/wireflow"

# Minimal Python file that the mock plan targets (agent/steps/issue_parser.py).
# Content is intentionally simple so repo_indexer can chunk and index it.
_ISSUE_PARSER_STUB = '''\
"""Issue parser stub — replace with real LLM classification call."""
from agent.context import RunContext, StepError


def run(ctx: RunContext) -> None:
    # TODO: call LLM to classify issue as bug_fix, feature, or refactor
    ctx.issue.task_type = "bug_fix"
'''


def _setup_wireflow() -> str:
    """(Re)create /tmp/wireflow as a minimal git repo ready for the pipeline."""
    repo_path = Path(WIREFLOW_PATH)
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True)

    repo = git.Repo.init(str(repo_path))
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "AutoPR Test")
        cfg.set_value("user", "email", "test@autopr.local")

    # Create the file the mock planner always targets
    target_dir = repo_path / "agent" / "steps"
    target_dir.mkdir(parents=True)
    (target_dir / "issue_parser.py").write_text(_ISSUE_PARSER_STUB)

    repo.index.add(["agent/steps/issue_parser.py"])
    repo.index.commit("chore: initial scaffold")

    return str(repo_path)


def main() -> None:
    repo_path = _setup_wireflow()
    print(f"Wireflow repo: {repo_path}\n")

    ctx = RunContext(
        issue=Issue(
            number=1,
            title="issue_parser missing implementation",
            body=(
                "The issue_parser stub always returns 'bug_fix' without calling the LLM. "
                "It should use a classification prompt to determine the correct task type."
            ),
            repo_owner="test-owner",
            repo_name="wireflow",
        ),
        repo_path=repo_path,
    )

    AgentController().run(ctx)

    print("=== step_log ===")
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
