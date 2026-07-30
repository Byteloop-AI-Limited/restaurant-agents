# Restaurant Agents

UV workspace for the independently deployed SFCS and Burger Nation WhatsApp agents.

Read [`CONSTITUTION.md`](CONSTITUTION.md) before changing the architecture.
Use the [`docs/` index](docs/README.md) for the platform glossary, domain model,
ADRs, feature guides, and interactive architecture guide.

## Workspace commands

```bash
uv sync --all-packages
uv run ruff check .
uv run pytest
```

The applications remain separate entrypoints:

- `sfcs_agent.main:app`
- `bnat_agent.main:app`

Deployment is manual and app-specific; see each `apps/<restaurant>/fly.toml`.
