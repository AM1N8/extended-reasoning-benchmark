"""Reasoning budget configuration mapping L1-L5 to model-specific parameters."""

from dataclasses import dataclass

from benchmark.clients.base import BudgetLevel


@dataclass
class BudgetConfig:
    """Configuration mapping a budget level to specific API behaviors."""

    level: BudgetLevel
    label: str
    description: str
    system_prompt_injection: str | None
    prompt_suffix: str | None
    api_params: dict


L5_COT_INJECTION = (
    "Before answering, explore all possible approaches. Verify your reasoning step by step. "
    "Check edge cases. If you reach a conclusion, try to disprove it. "
    "Only give your final answer after thorough verification."
)

BUDGET_CONFIGS: dict[BudgetLevel, BudgetConfig] = {
    BudgetLevel.BASELINE: BudgetConfig(
        level=BudgetLevel.BASELINE,
        label="baseline",
        description="Standard call, no reasoning boost",
        system_prompt_injection=None,
        prompt_suffix=None,
        api_params={"reasoning_effort": "low"},  # Fallback value, but standard call applies
    ),
    BudgetLevel.LIGHT: BudgetConfig(
        level=BudgetLevel.LIGHT,
        label="light",
        description="Low reasoning effort",
        system_prompt_injection=None,
        prompt_suffix="Think briefly step by step.",
        api_params={"reasoning_effort": "low", "thinkingBudget": 512},
    ),
    BudgetLevel.MEDIUM: BudgetConfig(
        level=BudgetLevel.MEDIUM,
        label="medium",
        description="Medium reasoning effort",
        system_prompt_injection=None,
        prompt_suffix="Think step by step carefully.",
        api_params={"reasoning_effort": "medium", "thinkingBudget": 2048},
    ),
    BudgetLevel.HIGH: BudgetConfig(
        level=BudgetLevel.HIGH,
        label="high",
        description="High reasoning effort",
        system_prompt_injection=None,
        prompt_suffix="Analyze thoroughly, consider edge cases.",
        api_params={"reasoning_effort": "high", "thinkingBudget": 8192},
    ),
    BudgetLevel.MAXIMUM: BudgetConfig(
        level=BudgetLevel.MAXIMUM,
        label="maximum",
        description="High reasoning effort with exhaustive system injection",
        system_prompt_injection=L5_COT_INJECTION,
        prompt_suffix="Analyze thoroughly, consider edge cases.",
        api_params={"reasoning_effort": "high", "thinkingBudget": 16384},
    ),
}


def apply_budget(prompt: str, model: str, budget: BudgetLevel) -> tuple[str, str | None, dict]:
    """Applies budget configuration rules for the given model.

    Args:
        prompt: The original user prompt.
        model: The model string identifier.
        budget: The requested budget level.

    Returns:
        A tuple of (final_user_prompt, system_prompt, extra_api_params).
    """
    config = BUDGET_CONFIGS[budget]
    final_prompt = prompt
    system_prompt = config.system_prompt_injection
    extra_params = {}

    # GitHub Models o1 / o3-mini uses reasoning_effort
    if "o1" in model or "o3" in model:
        if budget != BudgetLevel.BASELINE:
            extra_params["reasoning_effort"] = config.api_params["reasoning_effort"]

        # Add L5 system injection if specified
        if budget == BudgetLevel.MAXIMUM and system_prompt:
            pass  # We pass this out as system_prompt

    # Gemini uses thinkingConfig inside generationConfig
    elif "gemini" in model:
        if budget != BudgetLevel.BASELINE:
            extra_params["thinkingConfig"] = {"thinkingBudget": config.api_params["thinkingBudget"]}
        # Add system prompt injection
        if system_prompt:
            pass  # Returned as system_prompt

    # DeepSeek R1 and baselines use pure prompting strategies
    else:
        if budget == BudgetLevel.BASELINE:
            if "deepseek" not in model:
                pass  # Baseline
            else:
                extra_params["temperature"] = 0.3
        else:
            # Baseline and DeepSeek R1 augmentation
            if "deepseek" in model:
                # DeepSeek L5: inject exhaustive CoT
                if budget == BudgetLevel.MAXIMUM and system_prompt:
                    final_prompt += f"\n\n{system_prompt}"
                    system_prompt = None  # Injected directly
                elif config.prompt_suffix:
                    final_prompt += f"\n\n{config.prompt_suffix}"
            else:
                # Generic baselines
                suffix_map = {
                    BudgetLevel.LIGHT: "Step by step:",
                    BudgetLevel.MEDIUM: "Think carefully, show work.",
                    BudgetLevel.HIGH: "Explore all approaches.",
                    BudgetLevel.MAXIMUM: L5_COT_INJECTION,
                }
                if budget in suffix_map:
                    final_prompt += f"\n\n{suffix_map[budget]}"

    return final_prompt, system_prompt, extra_params
