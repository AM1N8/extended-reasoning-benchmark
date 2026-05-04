# Prompt 04 — API Client Wrappers

## Role & Mission

You are a backend engineer building **robust, production-grade API clients** for querying multiple LLM providers. You will implement the full client layer: a typed abstract base class, two concrete implementations (GitHub Models and Google AI Studio), and a unified dispatcher with rate limiting and exponential backoff.

---

## GLOBAL CONTEXT

```
Project: LLM benchmark — querying 6 models across 2 API providers
APIs:
  - GitHub Models REST API endpoint: https://models.inference.ai.azure.com
    Auth: Bearer {GITHUB_PAT}
    Models: openai/o1, openai/o3-mini, deepseek/DeepSeek-R1
    
  - Google AI Studio (Gemini)
    Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
    Auth: ?key={GOOGLE_AI_STUDIO_KEY}  
    Models: gemini-2.0-flash-thinking-exp
    
  - Baseline models (also via GitHub Models):
    openai/gpt-4o, claude-3-5-sonnet (via GitHub Models or Anthropic API)

Stack: Python 3.12+, httpx (async), pydantic, ruff-compatible style
Rate limits: Free tiers — aggressive rate limiting required
```

---

## The 5 Reasoning Budget Levels

This is critical — budget levels must translate to actual API parameters:

| Level | Name | GitHub Models (o1/o3) | DeepSeek R1 | Gemini Flash Thinking | Baseline |
|---|---|---|---|---|---|
| L1 | `baseline` | Standard call, no reasoning boost | temp=0.3, no CoT prompt | Standard | Standard |
| L2 | `light` | `reasoning_effort: "low"` | Add "Think briefly step by step" suffix | `thinkingConfig: {thinkingBudget: 512}` | Add "Step by step:" prefix |
| L3 | `medium` | `reasoning_effort: "medium"` | Add "Think step by step carefully." | `thinkingConfig: {thinkingBudget: 2048}` | Add "Think carefully, show work." |
| L4 | `high` | `reasoning_effort: "high"` | Add "Analyze thoroughly, consider edge cases." | `thinkingConfig: {thinkingBudget: 8192}` | Add "Explore all approaches." |
| L5 | `maximum` | `reasoning_effort: "high"` + system injection | Add exhaustive CoT injection (see below) | `thinkingConfig: {thinkingBudget: 16384}` | Add exhaustive CoT injection |

**L5 CoT system injection:**
```
"Before answering, explore all possible approaches. Verify your reasoning step by step. 
Check edge cases. If you reach a conclusion, try to disprove it. 
Only give your final answer after thorough verification."
```

---

## Module: `src/benchmark/clients/base.py`

### Abstract Base Class

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum

class BudgetLevel(IntEnum):
    BASELINE = 1
    LIGHT = 2
    MEDIUM = 3
    HIGH = 4
    MAXIMUM = 5

@dataclass
class ModelResponse:
    model: str
    prompt: str
    raw_trace: str | None           # <think> content or equivalent
    final_answer: str
    input_tokens: int
    reasoning_tokens: int           # 0 if not exposed by API
    output_tokens: int
    latency_seconds: float
    raw_api_response: dict          # Full JSON for debugging

@dataclass
class QueryRequest:
    prompt: str
    model: str
    budget_level: BudgetLevel
    max_tokens: int = 4096
    temperature: float = 0.0        # 0 for deterministic results

class BaseLLMClient(ABC):
    """Abstract base for all LLM API clients."""
    
    @abstractmethod
    async def query(self, request: QueryRequest) -> ModelResponse:
        """Send a query and return a structured response."""
    
    @abstractmethod
    def supports_model(self, model: str) -> bool:
        """Return True if this client handles the given model name."""
    
    @abstractmethod
    def get_supported_models(self) -> list[str]:
        """Return list of all model names this client supports."""
    
    def apply_budget_to_prompt(self, prompt: str, budget: BudgetLevel) -> str:
        """Default budget → prompt suffix injection. Override for API-level params."""
```

---

## Module: `src/benchmark/clients/github_models.py`

### GitHub Models Client

Implements calls to `https://models.inference.ai.azure.com/chat/completions` using the OpenAI-compatible REST API format.

```python
GITHUB_MODELS_SUPPORTED = [
    "openai/o1",
    "openai/o3-mini", 
    "deepseek/DeepSeek-R1",
    "openai/gpt-4o",
]
```

**Key implementation details:**

1. **Request format** — OpenAI-compatible `/chat/completions`:
```json
{
  "model": "o1",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "reasoning_effort": "high",
  "max_completion_tokens": 4096
}
```

2. **Reasoning token extraction**: For o1/o3, the response includes `usage.completion_tokens_details.reasoning_tokens`. For DeepSeek R1, extract the `<think>...</think>` block from the assistant message content.

3. **Trace extraction for DeepSeek R1**:
```python
import re

def _extract_deepseek_trace(content: str) -> tuple[str, str]:
    """Split <think>trace</think> from final answer."""
    match = re.search(r"<think>(.*?)</think>(.*)", content, re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", content
```

4. **Budget → API parameter mapping**: Apply `reasoning_effort` parameter for o1/o3 models. For DeepSeek R1, inject CoT suffixes into the user message.

---

## Module: `src/benchmark/clients/google_studio.py`

### Google AI Studio Client

Implements calls to the Gemini REST API.

Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={API_KEY}`

```python
GOOGLE_STUDIO_SUPPORTED = [
    "gemini-2.0-flash-thinking-exp-01-21",
]
```

**Key implementation details:**

1. **Request format**:
```json
{
  "contents": [{"parts": [{"text": "..."}], "role": "user"}],
  "generationConfig": {
    "temperature": 0,
    "maxOutputTokens": 4096,
    "thinkingConfig": {
      "thinkingBudget": 2048
    }
  }
}
```

2. **Thinking trace extraction**: The Gemini thinking model returns parts with `"thought": true`. Extract these separately:
```python
def _extract_gemini_thinking(response: dict) -> tuple[str, str]:
    """
    Parse Gemini response parts.
    Returns (thinking_trace, final_answer).
    Thinking parts have {"thought": true} in their part object.
    """
    candidates = response.get("candidates", [{}])
    parts = candidates[0].get("content", {}).get("parts", [])
    
    thinking = " ".join(p["text"] for p in parts if p.get("thought"))
    answer = " ".join(p["text"] for p in parts if not p.get("thought"))
    return thinking, answer
```

3. **Token counting**: Parse `usageMetadata.thoughtsTokenCount` for reasoning tokens.

---

## Module: `src/benchmark/clients/__init__.py` — Rate-Limited Dispatcher

This is the **most critical module** — all benchmark code goes through here.

```python
class RateLimitedDispatcher:
    """
    Routes requests to the correct client, enforces rate limiting,
    and implements exponential backoff with jitter.
    """
    
    def __init__(self, settings: Settings):
        self._clients: list[BaseLLMClient] = [
            GitHubModelsClient(settings.github_pat, settings.github_models_endpoint),
            GoogleStudioClient(settings.google_ai_studio_key),
        ]
        # Per-client rate limit state
        self._last_call: dict[str, float] = {}
        self._min_delay: dict[str, float] = {
            "github": 2.0,    # 2 seconds between GitHub Models calls
            "google": 1.5,    # 1.5 seconds between Google calls
        }
```

**Rate limiting logic:**

```python
async def query(
    self, 
    request: QueryRequest,
    max_retries: int = 5,
) -> ModelResponse | None:
    """
    Dispatch with:
    1. Pre-call delay (enforce minimum gap between calls)
    2. Exponential backoff on 429/503 errors
    3. Return None (not raise) on permanent failure — allows pipeline to continue
    """
    
    client = self._route(request.model)
    provider_key = self._get_provider_key(request.model)
    
    for attempt in range(max_retries):
        # 1. Enforce minimum delay
        await self._wait_if_needed(provider_key)
        
        try:
            response = await client.query(request)
            self._last_call[provider_key] = time.monotonic()
            return response
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Exponential backoff with jitter
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Rate limited (attempt {attempt+1}). Waiting {wait:.1f}s")
                await asyncio.sleep(wait)
            elif e.response.status_code in (500, 502, 503):
                wait = 5 * (attempt + 1)
                logger.warning(f"Server error {e.response.status_code}. Waiting {wait}s")
                await asyncio.sleep(wait)
            else:
                logger.error(f"HTTP {e.response.status_code} — giving up on this request")
                return None
    
    logger.error(f"All {max_retries} attempts failed for {request.model}")
    return None
```

---

## Budget Module: `src/benchmark/engine/budget.py`

```python
@dataclass
class BudgetConfig:
    level: BudgetLevel
    label: str
    description: str
    system_prompt_injection: str | None
    prompt_suffix: str | None
    api_params: dict  # Extra params merged into API request

BUDGET_CONFIGS: dict[BudgetLevel, BudgetConfig] = {
    BudgetLevel.BASELINE: BudgetConfig(...),
    BudgetLevel.LIGHT: BudgetConfig(...),
    # ... all 5 levels
}

def apply_budget(
    prompt: str,
    model: str,
    budget: BudgetLevel,
) -> tuple[str, str | None, dict]:
    """
    Returns: (final_user_prompt, system_prompt | None, extra_api_params)
    """
```

---

## Testing

Write `tests/test_clients.py` with:

1. **Mock test**: `TestGitHubModelsClient` — mock `httpx.AsyncClient.post` to return a realistic o1 response JSON. Verify that `reasoning_tokens` is correctly extracted from `usage.completion_tokens_details.reasoning_tokens`.

2. **Mock test**: `TestDeepSeekTraceExtraction` — verify `_extract_deepseek_trace()` correctly splits `<think>` content.

3. **Mock test**: `TestGeminiThinkingExtraction` — verify `_extract_gemini_thinking()` correctly separates thought parts from answer parts.

4. **Unit test**: `TestBudgetApplication` — verify that `apply_budget(prompt, "deepseek/DeepSeek-R1", BudgetLevel.MAXIMUM)` appends the L5 injection text.

5. **Unit test**: `TestRateLimiting` — verify that two consecutive calls to the dispatcher with the same provider key are separated by at least `min_delay` seconds.

---

## Requirements

- Use `httpx.AsyncClient` — **not** `requests`, **not** `aiohttp`
- All clients must be `async` — use `asyncio.run()` only at the top level
- Never hardcode API keys — always read from `Settings`
- Every `ModelResponse` must have `latency_seconds` measured with `time.monotonic()`
- Log every API call at DEBUG level: model, budget, token counts
- Log every error at WARNING or ERROR level with the full response body
- Use `ruff`-compatible style throughout

---

## Output Format

1. `src/benchmark/clients/base.py`
2. `src/benchmark/clients/github_models.py`
3. `src/benchmark/clients/google_studio.py`
4. `src/benchmark/clients/__init__.py` (dispatcher)
5. `src/benchmark/engine/budget.py`
6. `tests/test_clients.py`
