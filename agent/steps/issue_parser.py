"""Issue parser step — classifies the issue type.

Input: ctx.issue (title + body populated)
Output: sets ctx.issue.task_type to one of "bug_fix", "feature", "refactor"
"""

from agent.context import RunContext, StepError
from llm.client import get_client

VALID_TASK_TYPES = {"bug_fix", "feature", "refactor"}

SYSTEM_PROMPT = (
    "You are a classifier for GitHub issues. "
    "Given an issue title and body, respond with exactly one word: "
    "bug_fix, feature, or refactor. "
    "No punctuation, no explanation."
)


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
    user_msg = f"Title: {ctx.issue.title}\n\nBody: {ctx.issue.body}"
    raw = get_client().complete(system=SYSTEM_PROMPT, user=user_msg, max_tokens=10)
    task_type = raw.strip().lower()

    if task_type not in VALID_TASK_TYPES:
        raise StepError(
            f"issue_parser: LLM returned unexpected classification {raw!r}. "
            f"Expected one of {VALID_TASK_TYPES}."
        )

    ctx.issue.task_type = task_type
