"""Google AI Studio client implementation for Gemini models."""

import logging
import time

import httpx

from benchmark.clients.base import BaseLLMClient, ModelResponse, QueryRequest
from benchmark.engine.budget import apply_budget

logger = logging.getLogger(__name__)

GOOGLE_STUDIO_SUPPORTED = [
    "gemini-2.0-flash-thinking-exp-01-21",
]


def _extract_gemini_thinking(response: dict) -> tuple[str, str]:
    """Parse Gemini response parts.

    Returns (thinking_trace, final_answer).
    Thinking parts have {"thought": True} in their part object.
    """
    candidates = response.get("candidates", [{}])
    if not candidates:
        return "", ""

    parts = candidates[0].get("content", {}).get("parts", [])

    thinking = " ".join(p["text"] for p in parts if p.get("thought"))
    answer = " ".join(p["text"] for p in parts if not p.get("thought"))

    return thinking, answer


class GoogleStudioClient(BaseLLMClient):
    """Client for Google AI Studio REST API endpoint."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def supports_model(self, model: str) -> bool:
        return model in GOOGLE_STUDIO_SUPPORTED

    def get_supported_models(self) -> list[str]:
        return GOOGLE_STUDIO_SUPPORTED.copy()

    async def query(self, request: QueryRequest) -> ModelResponse:
        """Send a query to the Google AI Studio endpoint."""
        final_prompt, system_prompt, extra_params = apply_budget(
            request.prompt, request.model, request.budget_level
        )

        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{request.model}:generateContent?key={self.api_key}"
        )

        payload = {
            "contents": [{"parts": [{"text": final_prompt}], "role": "user"}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }

        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        if "thinkingConfig" in extra_params:
            payload["generationConfig"]["thinkingConfig"] = extra_params["thinkingConfig"]

        logger.debug(
            f"Google Studio query: {request.model} "
            f"| Budget: {request.budget_level.name} | Payload: {payload}"
        )

        start_time = time.monotonic()
        async with httpx.AsyncClient(http2=True, timeout=120.0) as client:
            response = await client.post(
                endpoint, headers={"Content-Type": "application/json"}, json=payload
            )
            response.raise_for_status()
            data = response.json()
        latency = time.monotonic() - start_time

        thinking_trace, final_answer = _extract_gemini_thinking(data)

        # Extract tokens
        usage = data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)

        # Some versions expose thoughtsTokenCount directly in usageMetadata
        reasoning_tokens = usage.get("thoughtsTokenCount", 0)

        return ModelResponse(
            model=request.model,
            prompt=request.prompt,
            raw_trace=thinking_trace if thinking_trace else None,
            final_answer=final_answer,
            input_tokens=input_tokens,
            reasoning_tokens=reasoning_tokens,
            output_tokens=output_tokens,
            latency_seconds=latency,
            raw_api_response=data,
        )
