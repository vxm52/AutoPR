"""CLI entry point for running the AutoPR pipeline.

Usage:
    python -m autopr.run --issue 42 --repo owner/repo
"""

import argparse
import sys

from agent.controller import AgentController
from agent.context import RunContext, Issue
from github_client.client import GitHubClient


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments with issue and repo.
    """
    parser = argparse.ArgumentParser(
        description="Run the AutoPR pipeline for a GitHub issue"
    )
    parser.add_argument(
        "--issue",
        type=int,
        required=True,
        help="GitHub issue number to process",
    )
    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="Repository in owner/name format",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point for the AutoPR CLI.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    args = parse_args()

    # Parse repo owner/name
    if "/" not in args.repo:
        print(f"Error: Invalid repo format '{args.repo}'. Use owner/name format.")
        return 1

    owner, name = args.repo.split("/", 1)

    # Fetch issue from GitHub
    gh_client = GitHubClient()
    issue = gh_client.get_issue(owner, name, args.issue)

    # Clone repo
    repo_path = gh_client.clone_repo(owner, name)

    # Create context and run pipeline
    ctx = RunContext(issue=issue, repo_path=repo_path)
    controller = AgentController()
    ctx = controller.run(ctx)

    # Print results
    print("\n=== Pipeline Complete ===")
    print(f"Steps: {len(ctx.step_log)}")
    for log in ctx.step_log:
        print(f"  {log}")

    if ctx.errors:
        print(f"\nErrors: {len(ctx.errors)}")
        for error in ctx.errors:
            print(f"  - {error}")
        return 1

    if ctx.pr_url:
        print(f"\nPR created: {ctx.pr_url}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
