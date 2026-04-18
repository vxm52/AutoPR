"""Mock LLM client for local development and pipeline testing.

Returns hardcoded responses based on keywords in the system prompt,
so the full pipeline can be exercised without hitting a real API.

Usage:
    Set USE_MOCK_LLM=true in the environment (or .env) and the
    get_client() factory in llm/client.py will return this instead
    of LLMClient.
"""

import json


MOCK_PLAN_JSON = json.dumps({
    "files_to_modify": [
        {
            "path": "agent/steps/issue_parser.py",
            "reason": "Needs classification logic added",
            "change_summary": "Add LLM call to classify issue as bug_fix, feature, or refactor",
        }
    ],
    "files_to_create": [],
    "reasoning": "The issue_parser stub is missing its implementation. Adding a classification prompt call is sufficient to resolve the issue.",
    "confidence": "high",
})


class MockLLMClient:
    """Hardcoded LLM responses for offline pipeline development.

    Detects which pipeline step is calling based on keywords in the
    system prompt and returns a realistic response for that step.
    """

    def complete(self, system: str, user: str, max_tokens: int = 2000) -> str:
        """Return a step-appropriate hardcoded response.

        Args:
            system: The system prompt (used for step detection).
            user: The user message (returned as-is for code_generator).
            max_tokens: Ignored — present for interface compatibility.

        Returns:
            A hardcoded response matching what the real LLM would return.
        """
        system_lower = system.lower()

        if "classify" in system_lower or "bug_fix" in system_lower or "feature" in system_lower or "refactor" in system_lower:
            return "bug_fix"

        if ("plan" in system_lower and "json" in system_lower) or "schema" in system_lower:
            return MOCK_PLAN_JSON

        if "editing a single source file" in system_lower:
            # The user message is "File: ...\n\nInstruction: ...\n\n{file_content}".
            # Return only the file content, mirroring what the real LLM returns.
            parts = user.split("\n\n", 2)
            return parts[2] if len(parts) >= 3 else user

        return "Mock response"
