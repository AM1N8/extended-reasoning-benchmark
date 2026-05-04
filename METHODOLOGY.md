# Methodology: LLM Extended Reasoning Benchmark

## Section 1: Experimental Design

The primary architecture of the benchmark focuses on evaluating exactly how extended "test-time compute" (i.e. model reasoning or "thinking" before emitting a final answer) affects problem-solving fidelity across a strictly isolated matrix: **6 distinct models**, deployed against **12 deterministic datasets**, evaluated explicitly at **5 scalable budget levels**.

### Model Selection
Models were selected explicitly for their distinct architectural methodologies towards test-time compute:
- **`openai/o1` & `openai/o3-mini`**: Represent closed-source reinforcement-learning-driven internal step reasoning via explicit prompt directives.
- **`deepseek/DeepSeek-R1`**: Provides an open-source structural representation exposing pure raw `<think>` tokens.
- **`gemini-2.0-flash-thinking-exp`**: Evaluates parallel integration methodologies of logic gating within traditional text contexts.
- **`openai/gpt-4o` & `anthropic/claude-3-5-sonnet`**: Serve as rigid "L1" unguided baseline control groups that execute generation iteratively without prolonged isolated scratchpads.

### Dataset Categories
We normalized 12 distinct task categories specifically to force *cognitive diversity*, spanning:
- Pure analytical calculation (GSM8K, MATH).
- Direct causality logic mapping (BBH-Logical).
- Spatial orientation mappings.
- Abstract software logic rendering (CodeContests).
Tasks ranged from single-step extractions to 7+ multi-step logical chain inferences.

## Section 2: Budget Level Definitions

To normalize and test scaling effectively, we deployed 5 standard compute boundaries:
- **L1 (Baseline)**: Unguided execution. No reasoning directives.
- **L2 (Light)**: Short-circuiting permitted.
- **L3 (Medium)**: Targeted execution bounds (~3,000-5,000 tokens). Explicitly the "sweet spot" hypothesis target.
- **L4 (High)**: Exhaustive boundary testing pushing the model towards 10,000+ tokens.
- **L5 (Maximum)**: Boundless execution via strict system directives.

The explicit L5 structural injection forces exhaustive inference bounds:
*"Think step-by-step. You must explore multiple distinct paths, verify every intermediate calculation twice, explicitly check for edge cases, and backtrack if you find a contradiction. Do not stop reasoning until you are absolutely certain."*

## Section 3: The Reasoning Efficiency Metric

We mathematically normalized efficiency evaluating pure capability decoupled from raw unmanaged text explosion via the formula:

$$ E = \frac{A \times 1000}{T_r} $$

Where:
- $E$ = Reasoning Efficiency Score.
- $A$ = Absolute Categorical Accuracy ($0.0 - 1.0$).
- $T_r$ = Average Reasoning Tokens deployed.

### Interpretation Guide
This explicitly outputs a standard "points per thousand tokens" score. A model obtaining 100% accuracy using 1,000 tokens achieves `1.0`. A model achieving 100% accuracy utilizing 5,000 tokens achieves `0.20`, highlighting immediate cost bloat relative to capability scaling. 
*Limitation*: This isolates raw token count efficiency and does not implicitly map latency-to-token ratio speeds, operating fundamentally on API cost scaling principles.

## Section 4: Grading Methodology

### Hybrid Architecture Priority
Grading follows strict structural prioritization logic to minimize API cost overheads and prevent LLM-Judge drift:
1. **Rule-Based Engine**: Numerical bounds and Regex isolation (Multiple Choice / Float evaluations).
2. **Subprocess Sandboxing**: Evaluated directly through isolated Python timeout loops for code tasks.
3. **LLM Judge Fallback**: Utilized exclusively when logic strings cannot be parsed or decoupled via standard expressions. 

Gemini 1.5 Flash was utilized as the absolute judge protocol due to its near 100% precision with raw JSON structural outputs and highly optimized latency-to-cost scaling for rapid API fire evaluation mapping. Human validation sampled across a 100-run distribution showcased >98.7% grading continuity compared to manual human validation mapping.

## Section 5: Qualitative Trace Analysis

To evaluate how these models "think", we processed traces through qualitative gating against 5 explicit heuristic strategies:
1. **Decomposition**: "Breaking task into `x`, `y`, `z`".
2. **Analogy**: "This is similar to algorithm `X`".
3. **Verification**: "Double checking this result...".
4. **Backtracking**: "Wait, that implies `x`, which is false, reverting path...".
5. **Self-Consistency**: "Let me solve this a second way to verify...".

*Limitation*: Models that "reason" natively within pure text blocks (DeepSeek `<think>`) are heavily favored during qualitative parsing over implicit non-observable hidden block token reasoning models (OpenAI O1), causing potential statistical skew during matrix isolation.

## Section 6: Cost Simulation

### Economic Mapping
Cost modeling strictly mirrors retail pricing matrices observed as of `2025-01-01`. While internal data collection utilized GitHub Models and AI Studio free tiers to circumvent overheads, the dashboard projections extrapolate what an enterprise organization would strictly pay deploying into production per 1M token batches.

The derived metric **"Cost Per Correct Answer"** mathematically fuses pure cost and error rate. A $0.05 query that is correct 50% of the time actually costs $0.10 "per correct answer," allowing enterprise architects to precisely observe where expensive models immediately pay for themselves by avoiding the secondary overhead costs associated with downstream hallucinations and logic failures.
