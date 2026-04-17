"""Code generator step — generates modified file content.

Input: ctx.plan, ctx.repo_path
Output: populates ctx.patches

For each file in plan.files_to_modify:
- Read current file content from disk
- Send a SEPARATE LLM call with: file content + change_summary
- Receive back complete modified file content (not a diff)
- Store as a FilePatch

IMPORTANT: Process files one at a time. Do not batch multiple files in one LLM call.
"""

from agent.context import RunContext
from llm.client import get_client


CODE_GENERATOR_SYSTEM_PROMPT = """You are editing a single source file based on a specific instruction.
Return ONLY the complete modified file content.
Do not include any explanation.
Do not use markdown code fences.
Do not add or remove imports unless the instruction requires it.
Preserve all existing code that is not directly related to the change."""


def run(ctx: RunContext) -> None:
    """Generate modified file content for each file in the plan.

    Reads each file to be modified, sends it to the LLM with the
    change instruction, and stores the result as a FilePatch.

    Args:
        ctx: RunContext with ctx.plan and ctx.repo_path set.

    Mutates:
        ctx.patches: Populated with FilePatch objects for each modified file.

    Raises:
        StepError: If code generation fails for any file.
    """
    raise NotImplementedError("code_generator.run not yet implemented")
