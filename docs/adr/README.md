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

## Creating an ADR

Use the next four-digit number and include:

1. Title, status, date, and decision owners.
2. Context and the concrete pressure requiring a decision.
3. Decision stated in enforceable language.
4. Consequences, including tradeoffs and follow-up work.
5. Code and documentation references.

Architectural changes must also satisfy `CONSTITUTION.md`; an ADR cannot
silently override the constitution.
