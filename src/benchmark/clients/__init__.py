"""Rate-Limited Dispatcher for LLM API calls."""

import asyncio
import logging
import random
import time

import httpx

from benchmark.clients.base import BaseLLMClient, BudgetLevel, ModelResponse, QueryRequest
from benchmark.clients.github_models import GitHubModelsClient
from benchmark.clients.google_studio import GoogleStudioClient
from benchmark.clients.groq_client import GroqClient
from benchmark.config import Settings

logger = logging.getLogger(__name__)


class RateLimitedDispatcher:
    """Routes requests to the correct client, enforces rate limiting,
    and implements exponential backoff with jitter.
    """

    def __init__(self, settings: Settings):
        self._clients: list[BaseLLMClient] = [
            GitHubModelsClient(settings.github_pat, settings.github_models_endpoint),
            GoogleStudioClient(settings.google_ai_studio_key),
            GroqClient(settings.groq_api_key),
        ]
        # Per-client rate limit state
        self._last_call: dict[str, float] = {}
        self._min_delay: dict[str, float] = {
            "github": 8.0,  # 8 seconds between GitHub Models calls (~7.5 RPM)
            "google": 2.0,  # 2 seconds between Google calls (~30 RPM)
            "groq": 2.0,  # 2 seconds between Groq calls (~30 RPM)
        }
        self._locks: dict[str, asyncio.Lock] = {
            "github": asyncio.Lock(),
            "google": asyncio.Lock(),
            "groq": asyncio.Lock(),
        }

    def _route(self, model: str) -> BaseLLMClient:
        """Find the appropriate client for the model."""
        for client in self._clients:
            if client.supports_model(model):
                return client
        raise ValueError(f"No client found supporting model: {model}")

    def _get_provider_key(self, model: str) -> str:
        """Map model to provider key for rate limits."""
        if "gemini" in model:
            return "google"
        if "groq" in model:
            return "groq"
        return "github"

    async def _wait_if_needed(self, provider_key: str) -> None:
        """Enforce minimum delay between calls for the same provider."""
        async with self._locks[provider_key]:
            now = time.monotonic()
            last_call = self._last_call.get(provider_key, 0.0)
            min_delay = self._min_delay.get(provider_key, 1.0)

            elapsed = now - last_call
            if elapsed < min_delay:
                wait_time = min_delay - elapsed
                await asyncio.sleep(wait_time)

            # Record execution time
            self._last_call[provider_key] = time.monotonic()

    async def query(
        self,
        request: QueryRequest,
        max_retries: int = 10,
    ) -> ModelResponse | None:
        """Dispatch a query with rate limiting and retry logic.

        Args:
            request: The standard query.
            max_retries: Maximum number of retry attempts for transient errors.

        Returns:
            The ModelResponse, or None if permanently failed.
        """
        client = self._route(request.model)
        provider_key = self._get_provider_key(request.model)

        for attempt in range(max_retries):
            # 1. Enforce minimum delay
            await self._wait_if_needed(provider_key)

            try:
                response = await client.query(request)
                return response

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 429:
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        wait = float(retry_after) + random.uniform(0.1, 1.0)
                    else:
                        # Stricter exponential backoff
                        wait = (2 ** (attempt + 2)) + random.uniform(0, 2)
                    logger.warning(f"Rate limited (attempt {attempt + 1}). Waiting {wait:.1f}s")
                    await asyncio.sleep(wait)
                elif status in (500, 502, 503, 504):
                    wait = 5 * (attempt + 1)
                    logger.warning(f"Server error {status}. Waiting {wait}s")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"HTTP {status} — giving up on this request for {request.model}")
                    logger.error(f"Response body: {e.response.text}")
                    return None
            except httpx.RequestError as e:
                # Network level errors
                wait = 2**attempt
                logger.warning(f"Network error: {e} (attempt {attempt + 1}). Waiting {wait}s")
                await asyncio.sleep(wait)

        logger.error(f"All {max_retries} attempts failed for {request.model}")
        return None
