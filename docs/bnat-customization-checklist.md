# BNAT Restaurant Customization Checklist

> [!WARNING]
> Do not deploy this scaffold to production traffic until every required item below
> has been reviewed and completed.

## Already configured

- [x] Repository bootstrapped from SFCS commit
  `ce46201ddf68ce082278ca94b4f5ffdf3ba35b7c`.
- [x] Canonical restaurant reference set to `BNAT`.
- [x] Fly application identity set to `bnat-agent`.
- [x] Production entrypoint retained as `watomation.fapp:app`.
- [x] Existing secret-loading code and secret values left unchanged.

## Customer-facing agent content

- [ ] Replace the Southern Fried Chicken welcome message in
  `rest_agent/agent_wa_senders.py`.
- [ ] Review every file under `rest_agent/agents/prompts/` for Southern Fried
  Chicken, Elai, Salisbury contact information, restaurant policies, supported
  services, and menu-specific instructions.
- [ ] Confirm that delivery, takeaway, dine-in, and triage behavior matches BNAT.

## WhatsApp messages and media

- [ ] Replace the restaurant name in `watomation/on_callback_handler.py`.
- [ ] Replace the SFCS logo URL in
  `services/wa_templates/rest_menu_wa_template.py` with an approved BNAT asset.
- [ ] Review `config/waba_setting.py` and confirm that the unchanged `lai`
  namespace is intentionally correct for BNAT before enabling traffic.
- [ ] Verify the configured WhatsApp callback URL, phone ID, verified name, and
  templates against the future `bnat-agent` deployment.

## Restaurant and Ordelo data

- [ ] Create or verify the `BNAT` row in `restaurant_master`, including admins,
  service hours, address, coordinates, supported order types, and stale-thread
  policy.
- [ ] Create or verify the `BNAT_APP_URL` Ordelo configuration value.
- [ ] Review SFCS-specific SQL examples under `services/ordelo_service/datamodels/`
  and `services/service_hours/`; do not execute them unchanged for BNAT.
- [ ] Verify menu, pricing, payment, maps, rider, reservation, and order-service
  configuration using BNAT data.

## Documentation and test cleanup

- [ ] Update `CLAUDE.md`, `agents.md`, and `docs/` where they describe SFCS,
  Elai, Southern Fried Chicken, or Salisbury-specific behavior.
- [ ] Decide whether SFCS/Elai identifiers in test fixtures are generic examples
  or should become BNAT-specific fixtures.
- [ ] Reconcile and restore `tests/test_single_restaurant_flow.py`; it was excluded
  from the bootstrap because its expectations already disagreed with the source
  SFCS agent and prompt.
- [ ] Review the inherited Ruff baseline and remove the 12 existing unused
  import/variable findings separately from restaurant customization.

## Production acceptance

- [ ] Classify every result from:

  ```bash
  rg -n -i 'sfcs|elai|southern fried|salisbury|sfc[ +_-]?logo' \
    --glob '!.venv/**' --glob '!uv.lock'
  ```

- [ ] Run the full retained test suite with no failures.
- [ ] Build the production Docker image successfully.
- [ ] Run authenticated `fly config validate --strict`.
- [ ] Confirm `/healthz`, WhatsApp webhook delivery, thread creation with a `BNAT`
  prefix, menu links, order creation, payment callbacks, and Ordelo event hooks in
  a non-production environment.
- [ ] Remove the production-readiness warning only after the checklist is complete.
