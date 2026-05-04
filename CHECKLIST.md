# Publication Readiness Checklist

Run through this checklist manually to ensure the repository is clean and deployment-ready for GitHub publication.

- [ ] `.env` is NOT committed (verify using `.gitignore`).
- [ ] All tests successfully pass (`just test`).
- [ ] No `ruff` styling or compliance errors exist (`just lint`).
- [ ] `README.md` features concrete, real-world analytical results (not placeholders).
- [ ] All required 6 figure visualizations correctly rendered as PNGs within `results/figures/`.
- [ ] The `enterprise_guide.md` has successfully generated natively via `just report`.
- [ ] The local SQLite database (`db/benchmark.db`) is NOT committed (verify using `.gitignore`).
- [ ] `uv.lock` IS structurally committed ensuring perfect upstream environment reproducibility.
