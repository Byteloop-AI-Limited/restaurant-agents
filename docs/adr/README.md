# Architecture Decision Records

ADRs preserve significant platform decisions and their consequences. They are
append-only decision history: do not rewrite an accepted ADR to change the
decision; add a new ADR that supersedes it.

## Status Vocabulary

- **Proposed**: under active discussion and not yet governing.
- **Accepted**: approved and governing current changes.
- **Superseded**: replaced by a later ADR, which must be linked.
- **Deprecated**: retained for history but no longer recommended.

## Index

| ADR | Status | Decision |
| --- | --- | --- |
| [0001](0001-platform-boundary-and-external-contexts.md) | Accepted | Platform boundary and external contexts |
| [0002](0002-independent-applications-share-one-runtime-package.md) | Accepted | Independent apps share one runtime package |
| [0003](0003-one-isolated-runtime-and-whatsapp-client-per-application.md) | Accepted | One isolated runtime and WhatsApp client per app |
| [0004](0004-app-owned-prompts-and-minimal-agent-customization.md) | Accepted | App-owned prompts and minimal Agent customization |
| [0005](0005-food-order-is-the-authoritative-order-aggregate.md) | Accepted | FoodOrder is the authoritative order aggregate |
| [0006](0006-external-payment-and-fulfilment-authority.md) | Accepted | External payment and fulfilment authority |
| [0007](0007-separate-restaurant-identity-presentation-and-master-data.md) | Accepted | Separate Restaurant identity, presentation, and master data |
| [0008](0008-markdown-is-the-documentation-source-of-truth.md) | Accepted | Markdown is the documentation source of truth |
| [0009](0009-canonical-food-order-model-without-catalog-writer.md) | Accepted | Canonical FoodOrder model without an internal catalog writer |
| [0010](0010-remove-live-whatsapp-simulation-commands.md) | Superseded | Remove live WhatsApp simulation commands from the shared runtime |
| [0011](0011-explicit-settings-composition-lifecycle.md) | Accepted | Load settings at the application composition root |
| [0012](0012-restore-paid3100-payment-simulation.md) | Accepted | Restore the `/paid3100` payment simulation |
| [0013](0013-runtime-rendered-prompts-and-service-order-cutoffs.md) | Accepted | Runtime-rendered prompts and service order cutoffs |
| [0014](0014-ordelo-owned-complaint-admin-notifications.md) | Accepted | Ordelo-owned complaint admin notifications |
| [0015](0015-app-owned-enquiry-menus.md) | Accepted | App-owned bounded enquiry menus |
| [0016](0016-runtime-owned-operational-lookup-cache.md) | Accepted | Runtime-owned operational lookup cache |

## Creating an ADR

Use the next four-digit number and include:

1. Title, status, date, and decision owners.
2. Context and the concrete pressure requiring a decision.
3. Decision stated in enforceable language.
4. Consequences, including tradeoffs and follow-up work.
5. Code and documentation references.

Architectural changes must also satisfy `CONSTITUTION.md`; an ADR cannot
silently override the constitution.
