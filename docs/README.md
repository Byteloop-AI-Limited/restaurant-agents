# Restaurant Platform Documentation

This directory is the canonical architecture and domain-knowledge entry point
for humans and coding agents. Markdown is the source of truth; interactive HTML
guides are secondary views.

## Start Here

1. Read the [platform glossary](glossary.md) for the repository's ubiquitous
   language.
2. Read the [platform domain model](domain/platform-domain-model.md) for bounded
   contexts, authority chains, records, commands, events, and external systems.
3. Read the [ADR index](adr/README.md) before changing a settled architecture
   decision.
4. Use the [shared multi-agent guide](multi_agent_system.md) for runtime
   composition, customization, and source navigation.
5. Use the [interactive Agent runtime guide](guides/agent-runtime-composition.html)
   as an optional visual companion.
6. Read the [architectural concepts primer](guides/architectural-concepts-primer.md)
   for the reasoning behind the composition patterns — module depth, domain
   models, partials, protocols, and a review checklist for generated code.

## Documentation Types

| Documentation | Purpose | Update when |
| --- | --- | --- |
| `glossary.md` | Defines terms used consistently across code and docs | A term is introduced, renamed, or changes meaning |
| `domain/platform-domain-model.md` | Maps contexts, authority, records, commands, and events | Ownership or data flow changes |
| `adr/` | Records durable architectural decisions and consequences | A significant decision is accepted, superseded, or reversed |
| Feature documents | Explain one implemented subsystem with human and machine-readable code maps | Its workflow, contracts, or edge cases change |
| `to-do.md` | Tracks deferred work without presenting it as an accepted decision | Deferred work is found, started, or completed |
| `guides/*.html` | Optional interactive views derived from canonical Markdown | The corresponding Markdown model changes materially |

## Feature Guides

- [Shared multi-agent orchestration](multi_agent_system.md)
- [Delivery Agent](delivery_whatsapp_agent.md)
- [Takeaway Agent](takeaway_whatsapp_agent.md)
- [Prompt ownership and change rules](rules-to-update-prompt-files.md)
- [Order management](order_management.md)
- [Payment system](payment_system.md)
- [Address and maps](address_maps_service.md)
- [Webhook endpoints](webhook_endpoints.md)
- [Service and Restaurant caches](caching_system.md)
- [BNAT customization checklist](bnat-customization-checklist.md)

## Documentation Rules

- Do not use an HTML guide as the only record of a rule or decision.
- Do not describe an external system's private internals as part of this
  repository's domain model.
- Distinguish authoritative persisted business state from runtime conversation
  state and incoming contract payloads.
- Follow the repository's hybrid Markdown convention: human-friendly relative
  links plus machine-readable `code-ref` blocks for important symbols.
- Preserve historical ADRs. Supersede them with a new ADR instead of rewriting
  the original decision.
