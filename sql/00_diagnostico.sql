-- SOLO LECTURA. Para el modelo oportunidades. No muestra UUIDs ni teléfonos.
select table_name,column_name,data_type,is_nullable,column_default
from information_schema.columns where table_schema='public' and table_name in
 ('leads','oportunidades','estado_oportunidad','visitas','estados_visita','propiedades','propiedad_imagenes')
order by table_name,ordinal_position;

select conrelid::regclass as tabla,conname,pg_get_constraintdef(oid)
from pg_constraint where connamespace='public'::regnamespace and conrelid in
 ('public.oportunidades'::regclass,'public.visitas'::regclass,'public.propiedad_imagenes'::regclass);
select * from public.estado_oportunidad order by id;
select * from public.estados_visita order by id;
select count(*) as oportunidades_incompletas from oportunidades where lead_id is null or token_uuid is null or estado_id is null;
select count(*) as visitas_incompletas from visitas where oportunidad_id is null or propiedad_id is null;
select count(*) as grupos_token_duplicado from (select 1 from oportunidades group by token_uuid having count(*)>1) q;
select lead_id,count(*) as abiertas from oportunidades where resultado is null and fecha_cierre is null group by lead_id having count(*)>1;
select oportunidad_id,count(*) as visitas from visitas group by oportunidad_id having count(*)>1;
select v.id from visitas v left join oportunidades o on o.id=v.oportunidad_id where o.id is null;
select i.id from propiedad_imagenes i left join propiedades p on p.id=i.propiedad_id where p.id is null;
select schemaname,tablename,policyname,roles,cmd from pg_policies where schemaname='public';
select event_object_table,trigger_name,action_statement from information_schema.triggers
where event_object_schema='public' and event_object_table in ('leads','oportunidades','visitas');
