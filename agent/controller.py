"""AgentController — sequential step runner for the AutoPR pipeline.

The controller runs steps sequentially. Each step is a plain function
that takes ctx and returns nothing. Steps raise StepError on unrecoverable failure.
"""

from agent.context import RunContext, StepError
from agent.steps import (
    issue_parser,
    repo_indexer,
    retriever,
    planner,
    code_generator,
    diff_generator,
    pr_creator,
)


PIPELINE = [
    issue_parser.run,
    repo_indexer.run,
    retriever.run,
    planner.run,
    code_generator.run,
    diff_generator.run,
    pr_creator.run,
]


class AgentController:
    """Orchestrates the AutoPR pipeline by running steps sequentially."""

    def run(self, ctx: RunContext) -> RunContext:
        """Execute all pipeline steps in sequence.

        Args:
            ctx: The RunContext containing the issue and shared state.

        Returns:
            The same RunContext, mutated by each step.
            Check ctx.errors and ctx.step_log for execution details.
        """
        for step_fn in PIPELINE:
            try:
                step_fn(ctx)
                ctx.step_log.append(f"OK  {step_fn.__module__}")
            except StepError as e:
                ctx.errors.append(str(e))
                ctx.step_log.append(f"ERR {step_fn.__module__}: {e}")
                break
        return ctx
