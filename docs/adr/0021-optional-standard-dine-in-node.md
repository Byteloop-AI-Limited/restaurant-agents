# ADR-0021: Optional Standard Dine-in Node

- Status: Accepted
- Date: 2026-08-17
- Decision owners: Restaurant platform owner and maintainers

## Context

ELAS books tables; the pre-monorepo `elai` monolith has a fourth agent,
`dinein_agent`, alongside triage/delivery/takeaway. The shared runtime's
graph is currently a fixed three-node contract, pinned by
`tests/rest_agent/test_graph_contract.py` and depended on by BNAT and SFCS.
Per the recorded architectural principle governing this repository (see the
`restaurant-agents-arch-principles` design record from the 2026-07-29
grill-me session), a new standard agent is "a deliberate core change when
first needed" — not something to add speculatively, and not something to
smuggle in behind an app-owned `GraphAdapter` when it doesn't need to be.

Whether dine-in requires that deliberate core change or an app-owned
`GraphAdapter` (ADR-0004's Tier 2) turns on one question: does it need
*incompatible* graph or state semantics, or is it one more node of the same
shape? `AgentState` already carries `reservation_id` and
`is_reservation_confirmed` (present before this change and otherwise
unused); `watomation/routers/reservation_hooks.py` and
`services/reservation_management/reservation_db_ops.py` are already
implemented in core but unmounted; and `elai`'s dine-in agent is two tools
plus the same three standard transfers, using the identical `Command` /
`/DoNotRespond:` contract every other standard agent uses. Nothing about it
is incompatible. An app-owned `GraphAdapter` would force ELAS to duplicate
`run_rest_graph_with_custom_msg`, the malformed-tool-call repair, and the
debug/state-inspection methods into `apps/elas` — copying a shared Agent
module to customize it, which `AGENTS.md` forbids outright.

## Decision

`dinein_agent` is a fourth **standard** node, added to the shared runtime,
activated only when an app supplies `RestaurantPrompts.dinein` (default
`None`). `build_multi_agent_graph` accepts an optional `dinein_agent_node`;
when omitted, node construction, routing, and the graph shape are
byte-for-byte what they were before this change. `route_initial` and
`route_after_agent` take an explicit `valid_agents` set (defaulting to the
three standard agents) rather than a hardcoded literal, so `dinein_agent` is
unreachable for any app that does not configure it — a value the caller
must explicitly widen, not a name the router recognizes by default.

`transfer_to_dinein` lives in `agent_harness.py` beside the other transfer
tools, using the same retained-work guard, and is appended to
triage/delivery/takeaway's tool lists only when `dinein_enabled` is true —
the same conditional-append pattern used for the restaurant-selection tools
(ADR-0020). It additionally checks
`RestaurantChoice.supports_dine_in`, so a multi-restaurant app can exclude
one brand from dine-in (Wings and Things, matching `elai`'s own behavior)
without a second core mechanism. `create_restaurant_app` gained
`include_reservation_router: bool = False` to mount the existing
`reservation_hooks` router only for apps that need it; the router already
enforces the `404` cross-restaurant contract via `runtime.identity.matches()`
and required no changes.

`STANDARD_AGENT_NAMES` in `agent_runner.py` becomes prompt-dependent:
`dinein_agent` is a valid `extra_tools_by_agent`/`agent_overrides` key only
when `prompts.dinein` is supplied, so an app that does not configure dine-in
still gets the documented `ValueError` for an unknown node name rather than
a silent no-op.

## Consequences

- BNAT and SFCS are unaffected: `build_multi_agent_graph(...)` called
  without `dinein_agent_node` produces the identical three-node graph, and
  their prompts never reference `transfer_to_dinein`.
- The shared AST-based graph-shape test could no longer distinguish "the
  unconditional baseline" from "the dine-in-configured graph" from source
  text alone, since both come from the same function with a runtime branch;
  `test_production_graph_has_the_standard_nodes_and_routes` now builds the
  real `StateGraph` both ways and inspects the constructed object instead of
  parsing source — a stronger characterization than the AST form gave up.
- A second app that needs dine-in reuses this node directly; a genuinely
  different specialist domain (a fifth standard agent) requires its own
  deliberate core decision, following the same reasoning as this ADR.

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/dine_in.py
symbol: build_dinein_agent
feature: optional-standard-dine-in-node
description: >
  Optional standard dine-in agent, constructed only when an app supplies a
  dine-in prompt.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/multi_agent.py
symbol: build_multi_agent_graph
feature: optional-standard-dine-in-node
description: >
  Accepts an optional dinein_agent_node; omitting it reproduces today's
  unconditional three-node graph exactly.
```

```code-ref
file: apps/elas/src/elas_agent/rest_agent/agent_recipe.py
symbol: PROMPTS
feature: optional-standard-dine-in-node
description: >
  ELAS supplies the dinein prompt that activates the fourth standard node.
```
