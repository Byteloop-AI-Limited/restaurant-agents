select * from thread order by dtts desc;

select dtts, * from thread where agent='SFCS' and recipient not in ('447919202938', '447448440754', '447446933210') order by dtts desc;
select * from cust_rest_map where rest_ref='SFCS';
select * from thread where recipient='447341964134';
exclude_list = ['447919202938', '447448440754', '447446933210'];

select * from customer_master;
select rest_ref, count(*) from cust_rest_map where has_consent group by rest_ref;
-- Check and close thread
select * from thread where is_active order by dtts desc;

update thread set is_active=False where is_active and recipient='447919202938';
update thread set is_active=False where is_active and thread_id='BNAT-5561cc96-d2fd-4787-83e4-9a3394f79dd7';



select * from cust_rest_map where cust_id='447448440754';
select * from customer_master where cust_id='447919202938';
select * from delivery_summary where order_number='ELAS-LIYF-22' order by dtts desc;
select * from delivery_summary order by dtts desc;
update delivery_summary set status='timedout' where order_number='SFCS-TIGD-21';
delete from cust_rest_map where cust_id='447448440754';
delete from customer_master where cust_id='447448440754';


SFCS-eee17ee8-b1f8-40e4-9bb6-a051d9ab52ac; SFCS-CJSR-23;
select * from delivery_dispatch where order_number='SFCS-CJSR-23' order by dtts desc;
update thread set is_active=false where is_active=True and dt<='2026-05-14' and agent='SFCS';
select * from thread where is_active=True and dt<'2026-03-27' order by dt desc;;
select * from food_order limit 1;
select * from rider_registrations order by inserted_at desc;

select pickup_time, * from delivery_summary where order_number='ELAS-ETXF-28';

SELECT dtts, dtts AT TIME ZONE 'Europe/London' as dtts_uk 
FROM delivery_summary 
WHERE order_number='ELAS-ETXF-27';

SELECT dtts, *
FROM delivery_summary 
WHERE order_number='BNAT-EEMF-24';

