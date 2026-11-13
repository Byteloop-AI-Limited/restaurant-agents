-- ============================================================
-- ELAS: Verification Queries
-- ============================================================
select admins, city, restaurant_start_time, * from restaurant_master where rest_ref in ('ELAS', 'CHKS');

select * from ordelo_config where config_key like 'ELAS_APP_URL';
select * from rider_master where rider_name in ('lohith', 'Bloop', 'Rahul');
-- ============================================================
-- ELAS: Test Setup
-- ============================================================
DO $$
BEGIN
    update restaurant_master
    -- set admins = Array['447919202938'],
    set admins = Array['447448440754'],
        rest_stale_active_threads_minutes = 10,
        restaurant_start_time = 11,
        service_hours_json = '{
    "mon": [["09:00", "24:00"]],
    "tue": [["00:00", "24:00"]],
    "wed": [["00:00", "24:00"]],
    "thu": [["00:00", "24:00"]],
    "fri": [["00:00", "24:00"]],
    "sat": [["00:00", "25:00"]],
    "sun": [["00:00", "21:00"]]
    }'::jsonb,
        restaurant_end_time = 24,
        city='dummy'
    where rest_ref in ('ELAS', 'CHKS');

    update elas_menu
    set title = 'TEST3100'
    where title='Naan';


    update rider_master
    set is_in_shift = true,
        status = 'active',
        town = 'dummy',
        vehicle_type = 'car'
        -- channel='whatsapp'
        -- channel='telegram'
    where rider_name = 'lohith';

    -- Cache reset call.
    PERFORM ordelo_post('ORDELO_APP_URL', '/internal/cache/reset');

END $$;

-- ============================================================
-- ELAS: Production Setup
-- ============================================================
--  447901518136 - Bineesh
--  919940742789 - Bineesh
--  447914844933 - Unni
--  447770114931 - Raj
--  447424792533 - Muthukumaran
DO $$
BEGIN

    update restaurant_master
    set admins = Array['447448440754', '447446933210','447901518136','447914844933', '447770114931', '447917912646', '919940742789'],
        rest_stale_active_threads_minutes = 10,
        city='Salisbury',
        service_hours_json = '{
            "mon": [["12:00", "22:00"]],
            "tue": [["12:00", "22:00"]],
            "wed": [["12:00", "22:00"]],
            "thu": [["12:00", "22:00"]],
            "fri": [["12:00", "22:00"]],
            "sat": [["12:00", "22:00"]],
            "sun": [["12:00", "21:00"]]
        }'::jsonb
    where rest_ref in ('ELAS', 'CHKS');


    update rider_master
    set is_in_shift = true,
        town = 'Salisbury',
        vehicle_type = 'bicycle'
    where rider_name = 'lohith';


    update elas_menu
    set title = 'Naan'
    where title='TEST3100';
    
    -- Cache reset call.
    PERFORM ordelo_post('ORDELO_APP_URL', '/internal/cache/reset');

END $$;



update ordelo_config set config_value = 'https://elas-agg.ordelo.app' where config_key = 'ELAS_APP_URL';

-- Cache reset calls, Should be run everytime after changing the app URL
SELECT * FROM ordelo_post('ORDELO_APP_URL', '/internal/cache/reset');

-- menu update

-- select * from  elas_menu;
-- 

INSERT INTO ordelo_config (config_key, config_value, description)
VALUES ('ELAS_RESTAURANT_CONFIRMATION_TIMEOUT_TIME', '.5', 'AutoAccept timeout in minutes') ON CONFLICT (config_key) DO
-- VALUES ('ELAS_DEFAULT_DELIVERY_PICKUP_TIME', '300', 'Default minutes to wait for restaurant confirmation before defaulting to max prep time') ON CONFLICT (config_key) DO
UPDATE
SET config_value = EXCLUDED.config_value,
    description = EXCLUDED.description;

select * from ordelo_config where config_key like 'ELAS%';
select * from ordelo_config where config_key like 'SFCS%';
-- ELAS_RESTAURANT_CONFIRMATION_TIMEOUT_TIME, ELAS_WEB_ORDERING_PAUSED - to be deleted.
select * from rider_master ;


