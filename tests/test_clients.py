"""Tests for API client wrappers and dispatcher."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from benchmark.clients.__init__ import RateLimitedDispatcher
from benchmark.clients.base import BudgetLevel, QueryRequest
from benchmark.clients.github_models import GitHubModelsClient, _extract_deepseek_trace
from benchmark.clients.google_studio import _extract_gemini_thinking
from benchmark.config import Settings
from benchmark.engine.budget import L5_COT_INJECTION, apply_budget


@pytest.fixture
def mock_settings():
    return Settings(
        github_pat="fake_pat",
        google_ai_studio_key="fake_key",
    )


@pytest.mark.asyncio
async def test_github_models_client():
    """Mock test for GitHubModelsClient verifying reasoning token extraction."""
    client = GitHubModelsClient("pat", "http://test")
    request = QueryRequest(prompt="Test", model="openai/o1", budget_level=BudgetLevel.BASELINE)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Final answer"}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 50,
            "completion_tokens_details": {"reasoning_tokens": 40},
        },
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        response = await client.query(request)

    assert response.final_answer == "Final answer"
    assert response.reasoning_tokens == 40
    assert response.input_tokens == 10
    assert response.output_tokens == 50


def test_deepseek_trace_extraction():
    """Verify _extract_deepseek_trace() correctly splits <think> content."""
    content = "<think>\nStep 1: calculate.\n</think>\nTherefore, 42."
    trace, answer = _extract_deepseek_trace(content)
    assert trace == "Step 1: calculate."
    assert answer == "Therefore, 42."

    # Missing think block
    trace, answer = _extract_deepseek_trace("Just 42.")
    assert trace == ""
    assert answer == "Just 42."


def test_gemini_thinking_extraction():
    """Verify _extract_gemini_thinking() correctly separates parts."""
    response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Let me think...", "thought": True},
                        {"text": "The answer is 42."},
                    ]
                }
            }
        ]
    }
    trace, answer = _extract_gemini_thinking(response)
    assert trace == "Let me think..."
    assert answer == "The answer is 42."


def test_budget_application():
    """Verify apply_budget injects suffixes and extra params appropriately."""
    # DeepSeek L5
    final, sys, params = apply_budget("Test", "deepseek/DeepSeek-R1", BudgetLevel.MAXIMUM)
    assert L5_COT_INJECTION in final
    assert sys is None  # Injected directly

    # o1 L4
    final, sys, params = apply_budget("Test", "openai/o1", BudgetLevel.HIGH)
    assert params["reasoning_effort"] == "high"
    assert final == "Test"

    # Gemini L3
    final, sys, params = apply_budget(
        "Test", "gemini-2.0-flash-thinking-exp-01-21", BudgetLevel.MEDIUM
    )
    assert params["thinkingConfig"]["thinkingBudget"] == 2048


@pytest.mark.asyncio
async def test_rate_limiting(mock_settings):
    """Verify dispatcher enforces minimum delays."""
    dispatcher = RateLimitedDispatcher(mock_settings)

    # We'll patch the Google client to just return immediately
    mock_client = AsyncMock()
    mock_client.supports_model.return_value = True
    mock_client.query.return_value = "Ok"

    # Patch the _route method to yield our mock
    dispatcher._route = MagicMock(return_value=mock_client)

    request = QueryRequest(prompt="A", model="gemini-fake", budget_level=BudgetLevel.BASELINE)

    start_time = time.monotonic()

    # Run two requests concurrently
    task1 = asyncio.create_task(dispatcher.query(request))
    task2 = asyncio.create_task(dispatcher.query(request))

    await asyncio.gather(task1, task2)
    end_time = time.monotonic()

    # The dispatcher enforces a 1.5s delay for google.
    # Therefore, the second call must wait ~1.5s after the first lock resolves.
    elapsed = end_time - start_time
    assert elapsed >= 1.4  # allow slight timing variance
