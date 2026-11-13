# CLAUDE.md

Read and follow [`AGENTS.md`](AGENTS.md) (it points to `CONSTITUTION.md` and the docs). It is the
repository's instruction file; this file only adds pointers for Claude.

@AGENTS.md

## Open to-dos to remember

- **Remove leftover restaurant-admin code.** This runtime must not talk to restaurant admins; OrdeloAgent
  owns every restaurant-facing message and button (WhatsApp and Telegram). The candidates, what to keep and
  the safety checks to run first are listed in [`docs/to-do.md`](docs/to-do.md), section
  "Remove leftover restaurant-admin code". Do not remove anything until those checks pass and the owner asks.
