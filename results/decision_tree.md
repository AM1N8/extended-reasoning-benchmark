
# Enterprise Model Selection Decision Tree

## Step 1: Task Complexity Assessment

Q: How many sequential deductive steps does this task require?

├── < 3 steps (simple lookup, classification, summarization)
│   └── → USE: GPT-4o or Claude 3.5 Sonnet (baseline)
│         Reason: Reasoning models provide no meaningful accuracy gain
│         Est. cost: $2–3 per 1,000 queries
│
├── 3–7 steps (math word problems, basic code, causal reasoning)  
│   └── → USE: DeepSeek R1 (Budget L3) or Gemini Flash Thinking (L3)
│         Reason: Sweet spot — substantial accuracy gain, moderate cost
│         Est. cost: $0.50–1.50 per 1,000 queries
│
└── > 7 steps (complex math, multi-step planning, hard coding)
    │
    ├── Latency-sensitive? (< 5s response time required)
    │   └── → USE: o3-mini (Budget L4)
    │         Reason: Best accuracy-per-latency trade-off
    │
    └── Latency-tolerant? (batch processing, offline)
        └── → USE: o1 (Budget L5) or DeepSeek R1 (Budget L5)
              Reason: Maximum accuracy, cost justified by task value

## Step 2: Budget Calibration

For the chosen model, use the minimum budget level that achieves 
your target accuracy threshold:

Target Accuracy   →  Recommended Budget Level
≥ 50%             →  L1 (baseline, cheapest)  
≥ 65%             →  L2 (light reasoning)
≥ 75%             →  L3 (medium — sweet spot for most tasks)
≥ 85%             →  L4 (high reasoning)
≥ 90%             →  L5 (maximum — use only when justified)

## Step 3: Cost Guardrails

Set a cost_per_correct_answer_usd threshold BEFORE production deployment.
If your threshold is exceeded at L3, do NOT escalate to L4/L5 — 
reconsider task formulation or dataset quality instead.
