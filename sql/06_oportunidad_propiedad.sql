-- Aplicar manualmente despues de 02 y 04. No elimina ni cierra datos historicos.
-- Diagnostico previo opcional:
-- select indexname,indexdef from pg_indexes where schemaname='public' and tablename='oportunidades';
-- select conname,pg_get_constraintdef(oid) from pg_constraint where conrelid='public.oportunidades'::regclass;
begin;
lock table public.oportunidades,public.visitas in share row exclusive mode;
alter table public.oportunidades add column if not exists propiedad_id bigint;
do $$
begin
  if exists(select 1 from public.oportunidades o join public.visitas v on v.oportunidad_id=o.id
    where o.propiedad_id is not null and o.propiedad_id is distinct from v.propiedad_id) then
    raise exception 'Hay oportunidades y visitas con propiedades distintas. Revisar sin sobrescribir.';
  end if;
  if exists(select 1 from public.oportunidades o left join public.visitas v on v.oportunidad_id=o.id
    where o.resultado is null and o.fecha_cierre is null
    group by o.lead_id,coalesce(o.propiedad_id,v.propiedad_id) having count(*)>1) then
    raise exception 'Hay oportunidades abiertas duplicadas por lead y propiedad (o exploracion). Resolver manualmente.';
  end if;
end $$;
-- El esquema anterior exigia una propiedad incluso antes de explorar.
alter table public.oportunidades drop constraint if exists oportunidades_abiertas_propiedad_nn;
alter table public.oportunidades alter column propiedad_id drop not null;
-- Recuperar solo la asociacion inequivoca de visitas ya existentes.
update public.oportunidades o set propiedad_id=v.propiedad_id from public.visitas v
where v.oportunidad_id=o.id and o.propiedad_id is null;
do $$
begin
  if not exists(select 1 from pg_constraint where conrelid='public.oportunidades'::regclass
    and contype='f' and confrelid='public.propiedades'::regclass
    and conkey=array[(select attnum from pg_attribute where attrelid='public.oportunidades'::regclass and attname='propiedad_id')]::smallint[]) then
    alter table public.oportunidades add constraint oportunidades_propiedad_id_fkey foreign key(propiedad_id) references public.propiedades(id);
  end if;
end $$;
create unique index if not exists ru_oportunidad_abierta_lead_propiedad_uq
on public.oportunidades(lead_id,propiedad_id) where resultado is null and fecha_cierre is null;
create unique index if not exists ru_oportunidad_exploracion_por_lead_uq
on public.oportunidades(lead_id) where propiedad_id is null and resultado is null and fecha_cierre is null;
-- Sustituye solamente el indice antiguo del repositorio: una abierta por lead.
drop index if exists public.ru_oportunidad_abierta_por_lead_uq;

create or replace function public.ru_solicitar_visita_oportunidad(
 p_token uuid,p_propiedad_id bigint,p_nombre text,p_fecha timestamptz,
 p_consentimiento boolean,p_request_id uuid,p_request_hash text,p_estado_nombre text,p_estado_oportunidad text
) returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare o public.oportunidades%rowtype; v public.visitas%rowtype;
 visit_state bigint; commercial_state bigint; state_count integer; owner_id bigint; conflict_name text;
begin
  select lead_id into owner_id from public.oportunidades where token_uuid=p_token;
  if not found then raise exception 'RU_TOKEN'; end if;
  perform id from public.leads where id=owner_id for update;
  select * into o from public.oportunidades where token_uuid=p_token for update;
  if not found then raise exception 'RU_TOKEN'; end if;
  if o.resultado is not null or o.fecha_cierre is not null then raise exception 'RU_CLOSED'; end if;
  if o.propiedad_id is not null and o.propiedad_id<>p_propiedad_id then raise exception 'RU_PROPERTY_MISMATCH'; end if;
  -- El bloqueo de oportunidad serializa solicitudes aunque las claves sean distintas.
  select * into v from public.visitas where oportunidad_id=o.id;
  if found then
    if v.request_id=p_request_id then
      if v.request_hash is distinct from p_request_hash then raise exception 'RU_REPLAY'; end if;
      return jsonb_build_object('id',v.id,'replayed',true);
    end if;
    raise exception 'RU_VISIT_EXISTS' using detail=v.id::text;
  end if;
  if p_request_id is null or p_request_hash is null or length(p_request_hash)<>64 then raise exception 'RU_REPLAY'; end if;
  if p_consentimiento is distinct from true then raise exception 'RU_CONSENT'; end if;
  if p_fecha is null or p_fecha<=clock_timestamp() then raise exception 'RU_DATE'; end if;
  if p_nombre is null or length(trim(p_nombre))<3 or length(trim(p_nombre))>120 then raise exception 'RU_NAME'; end if;
  perform id from public.propiedades where id=p_propiedad_id and disponible=true for share;
  if not found then raise exception 'RU_UNAVAILABLE'; end if;
  select min(id),count(*) into visit_state,state_count from public.estados_visita where nombre=p_estado_nombre;
  if state_count<>1 then raise exception 'RU_STATE: estado inicial de visita inexistente o ambiguo'; end if;
  select min(id),count(*) into commercial_state,state_count from public.estado_oportunidad where nombre=p_estado_oportunidad;
  if state_count<>1 then raise exception 'RU_STATE: estado visita_solicitada inexistente o ambiguo'; end if;
  if o.propiedad_id is null then
    if exists(select 1 from public.oportunidades where lead_id=o.lead_id and propiedad_id=p_propiedad_id
      and id<>o.id and resultado is null and fecha_cierre is null) then raise exception 'RU_PROPERTY_ALREADY_OPEN'; end if;
    update public.oportunidades set propiedad_id=p_propiedad_id where id=o.id;
  end if;
  -- Solo nombre existe en el esquema nuevo. No se escriben consentimiento_at,
  -- leads.updated_at ni estado comercial en leads.
  update public.leads set nombre=trim(p_nombre) where id=o.lead_id;
  if not found then raise exception 'RU_TOKEN'; end if;
  insert into public.visitas(oportunidad_id,propiedad_id,fecha_cliente,fecha_agente,fecha_acordada,estado_id,created_at,updated_at,request_id,request_hash)
    values(o.id,p_propiedad_id,p_fecha,null,null,visit_state,clock_timestamp(),clock_timestamp(),p_request_id,p_request_hash)
    returning * into v;
  update public.oportunidades set estado_id=commercial_state where id=o.id;
  -- resultado, fecha_cierre y motivo_perdida se conservan: solicitar no cierra.
  return jsonb_build_object('id',v.id,'replayed',false);
exception when unique_violation then
  get stacked diagnostics conflict_name = constraint_name;
  if conflict_name='ru_oportunidad_abierta_lead_propiedad_uq' then raise exception 'RU_PROPERTY_ALREADY_OPEN'; end if;
  raise;
end $$;

create or replace function public.ru_solicitar_visita_contacto(
 p_token uuid,p_propiedad_id bigint,p_nombre text,p_fecha timestamptz,
 p_consentimiento boolean,p_request_id uuid,p_request_hash text,p_estado_nombre text,p_estado_oportunidad text,p_telefono text
) returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare result jsonb; lead bigint;
begin
  if p_telefono is null or p_telefono !~ '^\+?[0-9]{7,15}$' then
    raise exception 'Telefono de WhatsApp invalido';
  end if;
  -- El RPC base bloquea lead y oportunidad en ese orden; conserva el bloqueo hasta commit.
  select lead_id into lead from public.oportunidades where token_uuid=p_token;
  result := public.ru_solicitar_visita_oportunidad(p_token,p_propiedad_id,p_nombre,p_fecha,
    p_consentimiento,p_request_id,p_request_hash,p_estado_nombre,p_estado_oportunidad);
  if not (result->>'replayed')::boolean then
    update public.leads set telefono=p_telefono where id=lead;
  end if;
  -- Si el telefono viola UNIQUE, toda la transaccion se revierte.
  return result;
end $$;
-- n8n conserva el mismo nombre y firma; solo reutiliza exploraciones abiertas.
create or replace function public.ru_obtener_o_crear_oportunidad(p_lead_id bigint)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare o public.oportunidades%rowtype; initial_state bigint; state_count integer;
begin
  perform id from public.leads where id=p_lead_id for update;
  if not found then raise exception 'RU_LEAD'; end if;
  select * into o from public.oportunidades where lead_id=p_lead_id and propiedad_id is null
    and resultado is null and fecha_cierre is null for update;
  if found then return jsonb_build_object('id',o.id,'token_uuid',o.token_uuid,'estado_id',o.estado_id,'reutilizada',true); end if;
  select min(id),count(*) into initial_state,state_count from public.estado_oportunidad where nombre='nuevo';
  if state_count<>1 then raise exception 'RU_STATE'; end if;
  insert into public.oportunidades(lead_id,estado_id,propiedad_id) values(p_lead_id,initial_state,null) returning * into o;
  return jsonb_build_object('id',o.id,'token_uuid',o.token_uuid,'estado_id',o.estado_id,'reutilizada',false);
end $$;

-- Resuelve el token por lead sin aceptar un lead_id enviado por el navegador.
create or replace function public.ru_resolver_oportunidad_propiedad(p_token uuid,p_propiedad_id bigint)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare source public.oportunidades%rowtype; target public.oportunidades%rowtype; exploration jsonb; owner_id bigint;
begin
  select lead_id into owner_id from public.oportunidades where token_uuid=p_token;
  if not found then raise exception 'RU_TOKEN'; end if;
  perform id from public.leads where id=owner_id for update;
  select * into source from public.oportunidades where token_uuid=p_token for share;
  if not found then raise exception 'RU_TOKEN'; end if;
  if source.resultado is not null or source.fecha_cierre is not null then raise exception 'RU_CLOSED'; end if;
  select * into target from public.oportunidades where lead_id=source.lead_id and propiedad_id=p_propiedad_id
    and resultado is null and fecha_cierre is null for update;
  if not found then
    perform id from public.propiedades where id=p_propiedad_id and disponible=true for share;
    if not found then raise exception 'RU_UNAVAILABLE'; end if;
    exploration:=public.ru_obtener_o_crear_oportunidad(source.lead_id);
    select * into target from public.oportunidades where id=(exploration->>'id')::bigint;
  end if;
  return jsonb_build_object('token_uuid',target.token_uuid,'propiedad_id',target.propiedad_id,
    'visita_id',(select id from public.visitas where oportunidad_id=target.id));
end $$;

revoke all on function public.ru_solicitar_visita_oportunidad(uuid,bigint,text,timestamptz,boolean,uuid,text,text,text) from public,anon,authenticated;
grant execute on function public.ru_solicitar_visita_oportunidad(uuid,bigint,text,timestamptz,boolean,uuid,text,text,text) to service_role;
revoke all on function public.ru_solicitar_visita_contacto(uuid,bigint,text,timestamptz,boolean,uuid,text,text,text,text) from public,anon,authenticated;
grant execute on function public.ru_solicitar_visita_contacto(uuid,bigint,text,timestamptz,boolean,uuid,text,text,text,text) to service_role;
revoke all on function public.ru_obtener_o_crear_oportunidad(bigint) from public,anon,authenticated;
grant execute on function public.ru_obtener_o_crear_oportunidad(bigint) to service_role;
revoke all on function public.ru_resolver_oportunidad_propiedad(uuid,bigint) from public,anon,authenticated;
grant execute on function public.ru_resolver_oportunidad_propiedad(uuid,bigint) to service_role;
notify pgrst,'reload schema';
commit;
