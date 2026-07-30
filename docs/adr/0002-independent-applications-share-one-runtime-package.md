# ADR-0002: Keep Independent Applications on One Shared Runtime Package

- Status: Accepted
- Date: 2026-07-29
- Decision owners: Repository owner and maintainers

## Context

SFCS and BNAT share most Agent, service, WhatsApp, and web behavior but must
remain operationally isolated and free to acquire genuinely custom behavior.
Duplicated implementations drift; one generic application would couple
identity, credentials, prompts, and releases too tightly.

## Decision

Maintain one Python/UV workspace with `restaurant-agent-runtime` for reusable
implementation and independent `sfcs-agent` and `bnat-agent` applications.
Applications may not import each other. The shared runtime may not import an
application package.

Each app owns identity, presentation, complete prompts, composition recipe,
entrypoint, deployment manifest, tests, and genuinely custom artifacts.

## Consequences

- Shared behavior is implemented and tested once.
- App identity, credentials, and deployments remain isolated.
- Compatible behavior needed by a second app is reviewed for promotion into the
  shared runtime rather than copied.
- Shared-runtime releases deploy both apps from the same repository revision.

## References

- `CONSTITUTION.md`
- `AGENTS.md`
- `docs/architecture/shared-agent-runtime-decisions.md`
