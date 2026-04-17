"""Diff generator step — creates unified diffs from patches.

Input: ctx.patches
Output: populates ctx.diffs

Uses difflib.unified_diff — do NOT ask the LLM to generate diffs.
Validates each diff applies cleanly with patch --dry-run before appending.
If a diff fails dry-run, log a warning and skip that file (do not raise).
"""

import difflib
from agent.context import RunContext, FilePatch


def make_diff(patch: FilePatch) -> str:
    """Generate a unified diff from a FilePatch.

    Args:
        patch: FilePatch containing original and modified content.

    Returns:
        Unified diff string.
    """
    return "".join(
        difflib.unified_diff(
            patch.original_content.splitlines(keepends=True),
            patch.modified_content.splitlines(keepends=True),
            fromfile=f"a/{patch.path}",
            tofile=f"b/{patch.path}",
        )
    )


def run(ctx: RunContext) -> None:
    """Generate unified diffs for all patches.

    Creates diffs using difflib (not LLM) and validates each
    can be applied cleanly.

    Args:
        ctx: RunContext with ctx.patches populated.

    Mutates:
        ctx.diffs: Populated with unified diff strings.

    Note:
        Does not raise on validation failure — skips invalid diffs
        with a warning logged to ctx.step_log.
    """
    raise NotImplementedError("diff_generator.run not yet implemented")
