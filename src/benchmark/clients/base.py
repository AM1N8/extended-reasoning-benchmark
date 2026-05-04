"""Abstract base for all LLM API clients."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum


class BudgetLevel(IntEnum):
    """Reasoning budget levels for LLM execution."""

    BASELINE = 1
    LIGHT = 2
    MEDIUM = 3
    HIGH = 4
    MAXIMUM = 5


@dataclass
class ModelResponse:
    """Structured response from any LLM API provider."""

    model: str
    prompt: str
    raw_trace: str | None
    final_answer: str
    input_tokens: int
    reasoning_tokens: int
    output_tokens: int
    latency_seconds: float
    raw_api_response: dict


@dataclass
class QueryRequest:
    """Standardized query request structure."""

    prompt: str
    model: str
    budget_level: BudgetLevel
    max_tokens: int = 4096
    temperature: float = 0.0


class BaseLLMClient(ABC):
    """Abstract base for all LLM API clients."""

    @abstractmethod
    async def query(self, request: QueryRequest) -> ModelResponse:
        """Send a query and return a structured response.

        Args:
            request: The standard query parameters.

        Returns:
            The structured model response.
        """

    @abstractmethod
    def supports_model(self, model: str) -> bool:
        """Return True if this client handles the given model name."""

    @abstractmethod
    def get_supported_models(self) -> list[str]:
        """Return list of all model names this client supports."""

    def apply_budget_to_prompt(self, prompt: str, budget: BudgetLevel) -> str:
        """Default budget suffix injection. Override for API-level params.

        Args:
            prompt: The original user prompt.
            budget: The configured reasoning budget.

        Returns:
            The augmented prompt.
        """
        # A simple default fallback; usually overridden in budget engine.
        return prompt
