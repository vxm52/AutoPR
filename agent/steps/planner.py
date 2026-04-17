"""Planner step — produces a structured modification plan.

Input: ctx.issue, ctx.retrieved_chunks
Output: populates ctx.plan

Uses TWO-PROMPT STRATEGY — planning is separate from code generation.
The LLM outputs JSON only, matching the Plan dataclass schema.
"""

from agent.context import RunContext


PLANNER_SYSTEM_PROMPT = """You are a senior engineer reviewing a GitHub issue.
Given the issue description and relevant code snippets, produce a structured plan.

Respond with JSON only. No explanation, no markdown fences.

Schema:
{
  "files_to_modify": [{"path": str, "reason": str, "change_summary": str}],
  "files_to_create": [{"path": str, "reason": str, "change_summary": str}],
  "reasoning": str,
  "confidence": "high" | "medium" | "low"
}

Rules:
- Only include files that were retrieved as relevant context
- Keep change_summary under 20 words
- Set confidence=low if the issue is ambiguous or requires information not in the snippets"""


def run(ctx: RunContext) -> None:
    """Generate a structured plan for addressing the issue.

    Sends the issue and retrieved chunks to the LLM, expecting
    a JSON response matching the Plan schema.

    Args:
        ctx: RunContext with ctx.issue and ctx.retrieved_chunks populated.

    Mutates:
        ctx.plan: Set to a Plan object parsed from LLM response.

    Raises:
        StepError: If LLM returns invalid JSON or low-confidence plan.
    """
    raise NotImplementedError("planner.run not yet implemented")
