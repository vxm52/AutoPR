"""PR creator step — creates branch, commits changes, opens pull request.

Input: ctx.patches, ctx.diffs, ctx.plan, ctx.issue
Output: sets ctx.pr_url

Steps:
1. Create branch (format: autopr/issue-{issue.number})
2. Apply patches to files
3. Commit changes
4. Push to remote
5. Open PR via GitHub API

Branch naming:
- Format: autopr/issue-{number}
- If branch exists, append -retry-{n}

PR format:
- Title: [AutoPR] {issue.title}
- Body: reasoning + summary of files changed + link to original issue

Uses GitPython for local git operations; PyGitHub for PR creation.
"""

from agent.context import RunContext


def run(ctx: RunContext) -> None:
    """Create a pull request with the generated changes.

    Creates a new branch, applies patches, commits, pushes,
    and opens a PR via the GitHub API.

    Args:
        ctx: RunContext with ctx.patches, ctx.diffs, ctx.plan, and ctx.issue set.

    Mutates:
        ctx.pr_url: Set to the URL of the created pull request.

    Raises:
        StepError: If branch creation fails or PR cannot be opened.
    """
    raise NotImplementedError("pr_creator.run not yet implemented")
