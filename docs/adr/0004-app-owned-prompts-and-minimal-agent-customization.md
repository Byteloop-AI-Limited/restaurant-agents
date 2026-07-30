# ADR-0004: Keep Prompts App-Owned and Agent Customization Minimal

- Status: Accepted
- Date: 2026-07-29
- Decision owners: Repository owner and maintainers

## Context

SFCS and BNAT share the standard graph but own different customer-facing
identity and may later diverge. A registry, recipe framework, or general node
extension API would add machinery before a second compatible need exists.

## Decision

Each app owns all three complete prompt files and binds a `RestaurantPrompts`
value to `RestaurantGraphAdapter` using `functools.partial`. The resulting
`GraphAdapterFactory` has the conceptual type
`RestaurantRuntime -> GraphAdapter`.

The standard adapter supports only `extra_tools_by_agent` for native tools on an
existing node and `agent_overrides` for a complete native runnable replacing an
existing node. New nodes or incompatible state, routing, handoff,
checkpointing, repair, or debug semantics require an app-owned GraphAdapter.

## Consequences

- Prompts never move into the shared package.
- Apps do not copy shared Agent modules to customize them.
- There is no node registry, recipe dataclass, plugin framework, or public
  per-agent factory layer.
- Framework-native LangChain, FastAPI, and PyWa objects remain the extension
  values.

## References

- `docs/multi_agent_system.md`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/prompts.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py`
- `apps/sfcs/src/sfcs_agent/rest_agent/agent_recipe.py`
- `apps/bnat/src/bnat_agent/rest_agent/agent_recipe.py`
