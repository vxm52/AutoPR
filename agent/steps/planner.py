"""Planner step — produces a structured modification plan.

Input: ctx.issue, ctx.retrieved_chunks
Output: populates ctx.plan

Uses TWO-PROMPT STRATEGY — planning is separate from code generation.
The LLM outputs JSON only, matching the Plan dataclass schema.
"""

import json

from agent.context import RunContext, Plan, FilePlan, StepError
from llm.client import get_client


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
    chunks_text = "\n\n".join(
        f"### {c.file}:{c.start_line}-{c.end_line} ({c.symbol})\n{c.content}"
        for c in ctx.retrieved_chunks
    )
    user_msg = (
        f"Issue #{ctx.issue.number}: {ctx.issue.title}\n\n"
        f"{ctx.issue.body}\n\n"
        f"Relevant code:\n{chunks_text}"
    )

    raw = get_client().complete(system=PLANNER_SYSTEM_PROMPT, user=user_msg)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise StepError(f"planner: LLM returned invalid JSON: {e}\nRaw response:\n{raw}") from e

    try:
        plan = Plan(
            files_to_modify=[FilePlan(**f) for f in data["files_to_modify"]],
            files_to_create=[FilePlan(**f) for f in data["files_to_create"]],
            reasoning=data["reasoning"],
            confidence=data["confidence"],
        )
    except (KeyError, TypeError) as e:
        raise StepError(f"planner: JSON missing required field: {e}\nRaw response:\n{raw}") from e

    if plan.confidence == "low":
        raise StepError(
            f"planner: confidence is low — issue may be ambiguous. "
            f"Reasoning: {plan.reasoning}"
        )

    ctx.plan = plan
