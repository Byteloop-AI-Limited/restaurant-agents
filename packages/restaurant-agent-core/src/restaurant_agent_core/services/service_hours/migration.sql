-- Migration: replace restaurant_start_time / restaurant_end_time with service_hours_json.
--
-- Run order:
--   1. Apply step 1 (adds the new column with a safe default).
--   2. UPDATE each restaurant row with the real weekly schedule (see examples.sql).
--   3. POST /restaurant-master-cache/reset to refresh in-memory caches.
--   4. Deploy the new application code.
--   5. Apply steps 2 + 3 (drops legacy columns, drops default).


-- Step 1 — add the JSONB column. NOT NULL with placeholder so existing rows stay valid.
alter table restaurant_master
  add column service_hours_json jsonb not null default '{}'::jsonb;


-- Step 2 — drop legacy float columns (run only after every restaurant has been backfilled
-- AND the new application code is deployed).
alter table restaurant_master drop column restaurant_start_time;
alter table restaurant_master drop column restaurant_end_time;


-- Step 3 — drop the placeholder default; new rows must specify service_hours_json explicitly.
alter table restaurant_master alter column service_hours_json drop default;
