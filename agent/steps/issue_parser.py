"""Issue parser step — classifies the issue type.

Input: ctx.issue (title + body populated)
Output: sets ctx.issue.task_type to one of "bug_fix", "feature", "refactor"
"""

from agent.context import RunContext
from llm.client import get_client


def run(ctx: RunContext) -> None:
    """Parse and classify the GitHub issue.

    Uses a simple LLM classification prompt to determine whether
    the issue is a bug fix, feature request, or refactoring task.

    Args:
        ctx: RunContext with ctx.issue populated.

    Mutates:
        ctx.issue.task_type: Set to "bug_fix", "feature", or "refactor".

    Raises:
        StepError: If classification fails.
    """
    raise NotImplementedError("issue_parser.run not yet implemented")
