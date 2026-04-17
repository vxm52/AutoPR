"""Thin wrapper around the course-provided LLM.

All LLM calls go through this client — do not call the model API
directly from step files.
"""

import os

import httpx


class LLMError(Exception):
    """Raised when an LLM call fails."""

    pass


class LLMClient:
    """Client for interacting with the course-provided LLM.

    Wraps the model API in a simple interface. All pipeline steps
    should use this client for LLM calls.
    """

    def __init__(self) -> None:
        """Initialize the LLM client with environment configuration."""
        self.api_key = os.environ.get("LLM_API_KEY")
        self.base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
        if not self.api_key:
            raise LLMError("LLM_API_KEY environment variable is not set")
        if not self.base_url:
            raise LLMError("LLM_BASE_URL environment variable is not set")

    def complete(self, system: str, user: str, max_tokens: int = 2000) -> str:
        """Send a completion request to the LLM.

        Args:
            system: The system prompt.
            user: The user message.
            max_tokens: Maximum tokens in the response.

        Returns:
            The assistant's text response.

        Raises:
            LLMError: If the API call fails.
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
        }

        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise LLMError(f"LLM API returned {e.response.status_code}: {e.response.text}") from e
        except httpx.RequestError as e:
            raise LLMError(f"LLM request failed: {e}") from e

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise LLMError(f"Unexpected LLM response format: {data}") from e


def get_client():
    """Return the appropriate LLM client based on environment configuration.

    Returns MockLLMClient when USE_MOCK_LLM=true, otherwise LLMClient.
    All pipeline steps should call this instead of instantiating LLMClient directly.
    """
    from llm.mock_client import MockLLMClient

    if os.environ.get("USE_MOCK_LLM", "").lower() == "true":
        return MockLLMClient()
    return LLMClient()
