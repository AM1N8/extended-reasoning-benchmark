# Contributing to LLM Extended Reasoning Benchmark

We welcome contributions to extend the benchmark's coverage across new models, new tasks, and deeper qualitative analysis methodologies.

## Adding a New Model
1. Subclass `BaseLLMClient` inside `src/benchmark/engine/clients/`.
2. Implement specific logic mapping your API's input protocol and explicit raw reasoning token extraction block handling.
3. Register the new model client within the main orchestration dispatcher pipeline.
4. Ensure you update `cost_dashboard.py` PRICING values matching standard API retail costs.

## Adding a New Dataset
1. Extend `DatasetLoader` from `src/benchmark/datasets/loader.py`.
2. Verify you map exactly to the normalized `DatasetStandardDataset` protocol (standardizing question structure and parsing criteria).
3. Append your new custom loader to `DATASET_REGISTRY` ensuring the pipeline correctly identifies and executes it during batch processing.

## Pull Request Requirements
- **Test Coverage**: All PRs must successfully pass the complete pytest matrix (`just test`). Any new models or dataset loaders must include respective tests targeting isolated mock calls.
- **Ruff Linting**: Ensure your code strictly passes formatting standards via `just lint`. Run `just format` and `just fix` prior to pushing your commits.
- **Type Annotations**: We enforce strict typing annotations globally (except within `tests/`). Ensure all functions expose definitive return types and typed schemas.
