"""FastAPI application for AutoPR.

Provides /run and /status endpoints for triggering and monitoring
the AutoPR pipeline.
"""

from fastapi import FastAPI

app = FastAPI(
    title="AutoPR",
    description="Autonomous developer agent that creates PRs from GitHub issues",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict:
    """Health check endpoint.

    Returns:
        Status dict indicating the service is running.
    """
    return {"status": "ok"}


@app.post("/run")
async def run_pipeline(issue_number: int, repo: str) -> dict:
    """Trigger the AutoPR pipeline for a GitHub issue.

    Args:
        issue_number: The GitHub issue number to process.
        repo: Repository in owner/name format.

    Returns:
        Dict with run_id and initial status.
    """
    raise NotImplementedError("/run endpoint not yet implemented")


@app.get("/status/{run_id}")
async def get_status(run_id: str) -> dict:
    """Get the status of a pipeline run.

    Args:
        run_id: The ID of the pipeline run.

    Returns:
        Dict with current status, step_log, errors, and pr_url if complete.
    """
    raise NotImplementedError("/status endpoint not yet implemented")
