# Figure Captions

**Figure 1: Accuracy vs Reasoning Tokens**
This scatter plot visualizes the non-linear relationship between the amount of test-time compute (reasoning tokens) and problem-solving accuracy. A LOWESS smoothing trendline per model reveals structural diminishing returns. The shaded "inflection zone" indicates where token investment ceases to yield proportional accuracy improvements.

**Figure 2: Reasoning Efficiency Heatmap**
This heatmap demonstrates the cost-effectiveness matrix across models and test-time compute budgets. Efficiency is calculated as accuracy per thousand reasoning tokens. Darker shades of red highlight Pareto-optimal deployment combinations.

**Figure 3: Accuracy by Budget Level**
A progression plot charting how individual model performance scales across budget constraints (L1 through L5). Solid lines indicate reasoning-capable models, while dashed lines plot traditional baselines. Inflection points (where marginal gains collapse below 2%) are highlighted with triangle markers.

**Figure 4: Strategy Effectiveness Matrix**
This qualitative analysis heatmap correlates the presence of explicit reasoning strategies (e.g., Backtracking, Decomposition) against ground-truth success rates across distinct task domains. A diverging colormap centered on the baseline unguided accuracy reveals which explicit strategies are actively harmful or highly beneficial.

**Figure 5: Cost vs Accuracy (Pareto Frontier)**
A macroeconomic scatter plot charting macro-average accuracy against estimated API costs. Point sizes are proportional to execution latency. A red step-line delineates the Pareto frontier, isolating model-budget combinations that provide maximal accuracy at their respective price points.

**Figure 6: Marginal Gain Waterfall**
This bar chart illustrates the exact percentage-point accuracy increase yielded by transitioning to the next successive budget tier. The red dashed line denotes the 2% significance threshold, establishing an algorithmic definition for diminishing returns.
