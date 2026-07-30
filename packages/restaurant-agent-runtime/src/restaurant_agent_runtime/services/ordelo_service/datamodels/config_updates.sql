select *
from ordelo_config where config_key like '%APP_URL%';

select * from ordelo_config where config_key like '%_APP_URL';
select * from ordelo_config where config_key like 'RESTAURANT_MENU%';
select * from ordelo_config where config_key like '%TIMEOUT%';

update ordelo_config set config_value = 'https://elas-agg-test.ordelo.app' where config_key = 'ELAS_APP_URL';
update ordelo_config set config_value = 'https://elas-agg.ordelo.app' where config_key = 'ELAS_APP_URL';

update ordelo_config
set config_value = 'https://elas-agg-test.ordelo.app'
where config_key = 'ELAS_APP_URL';

update ordelo_config set config_value = 'https://rider-agent-test.ordelo.app' where config_key = 'ORDELO_APP_URL';
update ordelo_config set config_value = 'https://rider-agent.ordelo.app' where config_key = 'ORDELO_APP_URL';

'https://3xxgnrawmh.eu-west-2.awsapprunner.com/'
update ordelo_config set config_value = 'https://3xxgnrawmh.eu-west-2.awsapprunner.com/' where config_key = 'SFCS_APP_URL';


update ordelo_config
set config_value = 'https://elas-agg.ordelo.app'
where config_key = 'ELAS_APP_URL';
update ordelo_config
set config_value = 'https://rider-agent.ordelo.app'
where config_key = 'ORDELO_APP_URL';



select * from food_order where order_id='OROT-53';