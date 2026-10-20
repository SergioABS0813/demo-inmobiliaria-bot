-- SOLO LECTURA. Ejecutar y revisar ANTES de 01_migracion.sql.
select table_name, column_name, data_type, is_nullable, column_default
from information_schema.columns where table_schema = 'public'
and table_name in ('leads','propiedades','propiedad_imagenes','distritos','visitas','estados_visita','estados_lead','agentes')
order by table_name, ordinal_position;

select conrelid::regclass as tabla, conname, pg_get_constraintdef(oid)
from pg_constraint where connamespace = 'public'::regnamespace
and conrelid in ('public.leads'::regclass,'public.propiedades'::regclass,
 'public.propiedad_imagenes'::regclass,'public.visitas'::regclass);

select * from public.estados_visita order by id;
select * from public.estados_lead order by id;
select count(*) as grupos_de_tokens_duplicados from
 (select 1 from public.leads where token_uuid is not null group by token_uuid having count(*)>1) q;
select i.id, i.propiedad_id from public.propiedad_imagenes i
left join public.propiedades p on p.id=i.propiedad_id where p.id is null;
select schemaname, tablename, policyname, roles, cmd from pg_policies where schemaname='public';
select event_object_table, trigger_name, action_statement from information_schema.triggers
where event_object_schema='public' and event_object_table in ('leads','visitas');
