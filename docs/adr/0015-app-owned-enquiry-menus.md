# ADR-0015: Keep Enquiry Menus App-Owned and Bounded

- Status: Superseded by [ADR-0023](0023-sectionlist-enquiry-menus.md)
- Date: 2026-08-03
- Decision owners: Restaurant platform owner and maintainers

## Context

SFCS and BNAT share triage callback handling but require different visible
enquiry choices. A shared hard-coded menu forced one restaurant's parking
option into the other and made future restaurant-level changes depend on shared
callback conditionals.

## Decision

Each application declares an immutable `EnquiryMenu` in its
`RestaurantPresentation`. The menu contains a prompt and one to three typed
`EnquiryOption` values. The standard sender serializes every option as a
`/SelectEnquiry` callback and the standard callback handler always enters
triage before running the graph.

`RestaurantPresentation` flows through the exact `RestaurantRuntime` and
`ContextSchema`, so both the callback and triage-tool paths use the same menu.
Prompt files remain app-owned policy for how triage responds after selection.

This is not a general callback registry. A genuinely new callback workflow
remains an app-owned native PyWa handler registered during app assembly.

## Consequences

- SFCS can hide parking while still handling a typed parking question according
  to its own triage prompt.
- BNAT can retain its parking option and policy without either app importing
  the other.
- Menu configuration is code-owned and changes require a coordinated release
  of both applications from the same shared-runtime revision.
- Existing legacy enquiry callback payloads remain accepted by the compatibility
  branch until no longer observed in active conversations.
