"""GitHub Models client implementation for OpenAI o1/o3 and DeepSeek R1."""

import logging
import re
import time
from typing import Any

import httpx

from benchmark.clients.base import BaseLLMClient, ModelResponse, QueryRequest
from benchmark.engine.budget import apply_budget

logger = logging.getLogger(__name__)

GITHUB_MODELS_SUPPORTED = [
    "openai/o1",
    "openai/o3-mini",
    "deepseek/DeepSeek-R1",
    "openai/gpt-4o",
]


def _extract_deepseek_trace(content: str) -> tuple[str, str]:
    """Split <think>trace</think> from final answer.

    Args:
        content: The raw string containing potential think blocks.

    Returns:
        A tuple of (thinking_trace, final_answer).
    """
    match = re.search(r"<think>(.*?)</think>(.*)", content, re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", content


class GitHubModelsClient(BaseLLMClient):
    """Client for GitHub Models REST API endpoint."""

    def __init__(self, pat: str, endpoint: str):
        self.pat = pat
        self.endpoint = endpoint.rstrip("/")
        if not self.endpoint.endswith("/chat/completions"):
            self.endpoint = f"{self.endpoint}/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.pat}",
            "Content-Type": "application/json",
        }

    def supports_model(self, model: str) -> bool:
        return model in GITHUB_MODELS_SUPPORTED

    def get_supported_models(self) -> list[str]:
        return GITHUB_MODELS_SUPPORTED.copy()

    async def query(self, request: QueryRequest) -> ModelResponse:
        """Send a query to the GitHub Models endpoint."""
        final_prompt, system_prompt, extra_params = apply_budget(
            request.prompt, request.model, request.budget_level
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": final_prompt})

        # Base payload
        payload: dict[str, Any] = {
            "model": request.model.split("/")[-1],
            "messages": messages,
            "max_completion_tokens": request.max_tokens,
        }

        # Handle temperature
        if "o1" not in request.model and "o3" not in request.model:
            payload["temperature"] = request.temperature

        # Override temp if extra_params specifies it (e.g. deepseek baseline)
        if "temperature" in extra_params:
            payload["temperature"] = extra_params["temperature"]

        # Add reasoning_effort for o1/o3
        if "reasoning_effort" in extra_params:
            payload["reasoning_effort"] = extra_params["reasoning_effort"]

        logger.debug(
            f"GitHub Models query: {request.model} "
            f"| Budget: {request.budget_level.name} | Payload: {payload}"
        )

        start_time = time.monotonic()
        async with httpx.AsyncClient(http2=True, timeout=120.0) as client:
            response = await client.post(self.endpoint, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
        latency = time.monotonic() - start_time

        # Extract message content
        choice = data["choices"][0]
        content = choice.get("message", {}).get("content", "")

        # Extract tokens
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        reasoning_tokens = 0

        raw_trace = None
        final_answer = content

        # Reasoning traces
        if "deepseek" in request.model.lower():
            raw_trace, final_answer = _extract_deepseek_trace(content)
            # Estimate reasoning tokens if trace exists and not explicitly given
            # In some deepseek implementations it might be in usage
            reasoning_tokens = len(raw_trace.split()) if raw_trace else 0

            # Or if API exposes it specifically:
            completion_details = usage.get("completion_tokens_details", {})
            if "reasoning_tokens" in completion_details:
                reasoning_tokens = completion_details["reasoning_tokens"]

        elif "o1" in request.model or "o3" in request.model:
            completion_details = usage.get("completion_tokens_details", {})
            if "reasoning_tokens" in completion_details:
                reasoning_tokens = completion_details["reasoning_tokens"]

        return ModelResponse(
            model=request.model,
            prompt=request.prompt,
            raw_trace=raw_trace,
            final_answer=final_answer,
            input_tokens=input_tokens,
            reasoning_tokens=reasoning_tokens,
            output_tokens=output_tokens,
            latency_seconds=latency,
            raw_api_response=data,
        )
