-- ============================================================
-- BNAT: Verification Queries
-- ============================================================

select admins, city, * from restaurant_master where rest_ref = 'BNAT';

select * from ordelo_config where config_key like '%BNAT_APP_URL';

select * from rider_master where rider_name in ('Lohith', 'Rahul', 'Bloop');
select * from rider_master where is_in_shift = true;
-- ============================================================
-- BNAT: Test Setup
-- ============================================================

update restaurant_master
-- set admins = Array['447919202938', '447448440754'],
-- 447936359321 - azz
-- 447932085625 - bab
set admins = Array['447919202938', '447932085625', '447936359321'],
    rest_stale_active_threads_minutes = 10,
    auto_accept = true,
    city='Orpington',
    service_hours_json = '{
  "mon": [["11:00", "23:00"]],
  "tue": [["11:00", "23:00"]],
  "wed": [["11:00", "23:00"]],
  "thu": [["11:00", "23:00"]],
  "fri": [["11:00", "23:00"]],
  "sat": [["11:00", "23:00"]],
  "sun": [["11:00", "23:00"]]
}'::jsonb
where rest_ref='BNAT';

update ordelo_config set config_value = 'https://rest-agent-test.ordelo.app' where config_key = 'BNAT_APP_URL';

-- Cache reset calls, Should be run everytime after changing the app URL
SELECT * FROM ordelo_post('BNAT_APP_URL', '/internal/cache/reset');
SELECT * FROM ordelo_post('BNAT_APP_URL', '/restaurant-master-cache/reset');


update rider_master
set is_in_shift = true,
    town = 'dummy',
    vehicle_type = 'car'
where rider_name = 'Rahul';


update rider_master
set is_in_shift = true,
    town = 'Orpington',
    vehicle_type = 'car'
where rider_name = 'Lohith';

update rider_master
set is_in_shift = true,
    town = 'dummy',
    vehicle_type = 'scooter'
where rider_name = 'Lohith';

update rider_master
set is_in_shift = true,
    town = 'dummy',
    vehicle_type = 'car'
where rider_name = 'Bloop';


select enquire_admin_availability(ARRAY['SFCS']);
-- ============================================================
-- BNAT: Production Setup
-- ============================================================

'447827180109' - Mi
'447769081769' - SFCS Admin number2
'447312083527' - Srj
'447446933210' - Rh
'447919202938' - Bl;

update restaurant_master
set admins = Array[ '447446933210','447919202938','447827180109', '447769081769', '447312083527'],
    rest_stale_active_threads_minutes = 10,
    city='Orpington',
    service_hours_json = '{
  "mon": [["11:00", "23:00"]],
  "tue": [["11:00", "23:00"]],
  "wed": [["11:00", "23:00"]],
  "thu": [["11:00", "23:00"]],
  "fri": [["11:00", "23:00"]],
  "sat": [["11:00", "23:00"]],
  "sun": [["11:00", "23:00"]]
}'::jsonb
where rest_ref = 'BNAT';

update ordelo_config set config_value = 'https://bnat-agent.fly.dev' where config_key = 'BNAT_APP_URL';

update rider_master
set is_in_shift = true,
    town = 'Salisbury',
    vehicle_type = 'bicycle'
where rider_name = 'Lohith';

update rider_master
set is_in_shift = true,
    town = 'Salisbury',
    vehicle_type = 'bicycle'
where rider_name = 'Bloop';



-- Cache reset calls, Should be run everytime after changing the app URL
SELECT * FROM ordelo_post('BNAT_APP_URL', '/restaurant-base-url-cache/reset');
SELECT * FROM ordelo_post('BNAT_APP_URL', '/restaurant-master-cache/reset');