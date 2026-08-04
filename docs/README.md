# Maiplot Documentation

The canonical project documentation lives at the workspace root, one level up from this repository.

| Document | Location | Purpose |
| --- | --- | --- |
| `CLAUDE.md` | `../../CLAUDE.md` | Project master context, non-negotiables, business rules |
| `plan.md` | `../../plan.md` | Milestone tasks and sprint tracker |
| `workflow.md` | `../../workflow.md` | Development workflow and operating procedure |
| `review.md` | `../../review.md` | Architecture-review checklist (must pass before every PR) |
| `data-model.md` | `../../data-model.md` | Full database schema |
| `api-contracts.md` | `../../api-contracts.md` | All API endpoint contracts |

## Repository-local documents

Unlike the table above, these live in this repository because they must be reviewable inside a pull request.

| Document | Location | Purpose |
| --- | --- | --- |
| `design-spec.md` | `./design-spec.md` | Measured design values — palette, spacing, radii, shadows, type, and drift vs. current code |
| `design-index.md` | `./design-index.md` | Maps every Figma PNG export to its screen and app route |

Both are generated from the exports in `frontend/web/design/`, which are gitignored. The tooling that produced them is in [`scripts/design/`](../scripts/design/).

Service-specific docs (runbooks, ADRs, OpenAPI specs) live next to each service under `services/<name>/docs/` once they exist.
