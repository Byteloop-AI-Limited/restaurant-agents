# ADR-0008: Make Markdown the Documentation Source of Truth

- Status: Accepted
- Date: 2026-07-30
- Decision owners: Repository owner and maintainers

## Context

Humans benefit from visual HTML guides, while coding agents reliably discover
repository instructions and text documentation. A visual artifact alone can be
missing, stale, or invisible to a future agent run.

## Decision

`docs/README.md`, `docs/glossary.md`, the domain model, ADRs, and feature
Markdown are canonical. `AGENTS.md` points future coding agents to them and
defines when they must be updated.

Interactive HTML is a secondary view. Every architectural rule shown in HTML
must also exist in canonical Markdown. Machine-readable `code-ref` blocks map
important concepts to implemented symbols.

## Consequences

- HTML can optimize exploration without becoming an independent specification.
- Broken or missing HTML never removes the governing written model.
- New constructs update glossary/domain/feature docs and machine-readable
  references together.
- Significant architectural reversals require a superseding ADR.

## References

- `AGENTS.md`
- `docs/README.md`
- `docs/documentation_prompt.md`
- `docs/guides/agent-runtime-composition.html`
