-- Example UPDATEs for restaurant_master.service_hours_json
--
-- JSONB shape: {"<weekday_key>": [["HH:MM", "HH:MM"], ...], ...}
--   . Weekday keys: "mon", "tue", "wed", "thu", "fri", "sat", "sun"
--   . Each day is a list of [open, close] pairs (split shifts allowed)
--   . Closed day: empty list
--   . Overnight: close = "24:00" (midnight) or "25:00" (1am next day), up to "48:00"
--   . Open/close inclusivity: open <= now < close (closing minute counts as closed)
--
-- After updating, hit POST /restaurant-master-cache/reset?rest_ref=<rest_ref>
-- to flip live within the 5-minute cache window.

select * from restaurant_master where rest_ref = 'SFCS';
-- Example 1 — open every day, 5pm to 9:30pm
update restaurant_master
set service_hours_json = '{
  "mon": [["17:00", "21:30"]],
  "tue": [["17:00", "21:30"]],
  "wed": [["17:00", "21:30"]],
  "thu": [["17:00", "21:30"]],
  "fri": [["17:00", "21:30"]],
  "sat": [["17:00", "21:30"]],
  "sun": [["17:00", "21:30"]]
}'::jsonb
where rest_ref = 'SFCS';


-- Example 2 — Mon-Fri 4pm to midnight; Sat-Sun 4pm to 1am next day
update restaurant_master
set service_hours_json = '{
  "mon": [["16:00", "24:00"]],
  "tue": [["16:00", "24:00"]],
  "wed": [["16:00", "24:00"]],
  "thu": [["16:00", "24:00"]],
  "fri": [["16:00", "24:00"]],
  "sat": [["16:00", "25:00"]],
  "sun": [["16:00", "25:00"]]
}'::jsonb
where rest_ref = 'SFCS';
