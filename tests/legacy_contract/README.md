# Superseded direct-module contract tests

These tests were copied from SFCS as provenance but directly load the former
top-level `config`, `services`, `watomation`, and `rest_agent` files and assert
module-global WhatsApp clients. Those contracts were intentionally removed by
the monorepo constitution.

They are excluded from collection. Equivalent workspace-level coverage lives in
`tests/test_runtime_isolation.py`; reusable pure service tests remain active in
the normal test tree.
