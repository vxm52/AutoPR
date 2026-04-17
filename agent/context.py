"""RunContext and related dataclasses for the AutoPR pipeline.

Every step receives and mutates a single RunContext. Steps do not pass
return values between each other — they read from and write to ctx only.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Issue:
    """Represents a GitHub issue to be processed."""

    number: int
    title: str
    body: str
    repo_owner: str
    repo_name: str
    task_type: str = ""  # "bug_fix" | "feature" | "refactor" — set by issue_parser


@dataclass
class RetrievedChunk:
    """A code chunk retrieved from the FAISS index."""

    file: str
    symbol: str
    start_line: int
    end_line: int
    content: str
    score: float


@dataclass
class FilePlan:
    """Plan for modifying or creating a single file."""

    path: str
    reason: str
    change_summary: str


@dataclass
class Plan:
    """Structured plan produced by the planner step."""

    files_to_modify: list[FilePlan]
    files_to_create: list[FilePlan]
    reasoning: str
    confidence: str  # "high" | "medium" | "low"


@dataclass
class FilePatch:
    """Original and modified content for a single file."""

    path: str
    original_content: str
    modified_content: str


@dataclass
class RunContext:
    """Shared state passed through all pipeline steps.

    This is the only inter-step interface. Steps do not call each other
    and do not return values — they read from and write to this context.
    """

    issue: Issue
    repo_path: str
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    plan: Optional[Plan] = None
    patches: list[FilePatch] = field(default_factory=list)
    diffs: list[str] = field(default_factory=list)
    pr_url: Optional[str] = None
    errors: list[str] = field(default_factory=list)
    step_log: list[str] = field(default_factory=list)


class StepError(Exception):
    """Raised by pipeline steps on unrecoverable failure."""

    pass
