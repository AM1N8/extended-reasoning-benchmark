import logging
import re

import httpx

from benchmark.clients.base import BaseLLMClient, ModelResponse, QueryRequest

logger = logging.getLogger(__name__)

GROQ_SUPPORTED = [
    "groq/deepseek-r1-distill-llama-70b",
    "groq/deepseek-r1-distill-qwen-32b",
    "groq/llama-3.3-70b-versatile",
]


class GroqClient(BaseLLMClient):
    """Client for Groq API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def supports_model(self, model: str) -> bool:
        return model in GROQ_SUPPORTED

    def get_supported_models(self) -> list[str]:
        return GROQ_SUPPORTED.copy()

    async def query(self, request: QueryRequest) -> ModelResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Format model name (strip groq/ prefix)
        model_name = request.model.replace("groq/", "")

        payload = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": request.prompt}
            ],
            "temperature": request.temperature,
            "max_completion_tokens": request.max_tokens,
        }

        if "JSON object" in request.prompt or "```json" in request.prompt:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(self.endpoint, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Groq API error {e.response.status_code}: {e.response.text}")
                raise

        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        # Groq doesn't natively split reasoning tokens in usage right now
        # We'll just count total output tokens, and we extract <think> blocks
        reasoning_tokens = 0

        content = data["choices"][0]["message"].get("content", "")

        # Extract reasoning from <think> tags if present
        raw_trace = ""
        final_answer = content

        think_match = re.search(r"<think>(.*?)</think>", content, flags=re.DOTALL)
        if think_match:
            raw_trace = think_match.group(1).strip()
            final_answer = content.replace(think_match.group(0), "").strip()
            # Approximation of reasoning tokens (Groq doesn't expose it distinctly yet)
            # Roughly 1 token per 4 characters
            reasoning_tokens = len(raw_trace) // 4
            output_tokens = output_tokens - reasoning_tokens

        return ModelResponse(
            model=request.model,
            prompt=request.prompt,
            raw_trace=raw_trace,
            final_answer=final_answer,
            input_tokens=input_tokens,
            reasoning_tokens=reasoning_tokens,
            output_tokens=max(0, output_tokens),
            latency_seconds=0.0,  # Computed at dispatcher level
            raw_api_response=data,
        )
