-- Aplicar MANUALMENTE sobre el esquema de oportunidades proporcionado.
-- No ejecutar 01_migracion.sql: pertenece al modelo anterior.
-- Ejecutar antes 00_diagnostico.sql. Transacción: ante inconsistencias se aborta
-- sin eliminar ni reasignar leads, oportunidades o visitas históricas.
begin;

do $$
begin
  if exists(select 1 from oportunidades where lead_id is null or token_uuid is null or estado_id is null) then
    raise exception 'Hay oportunidades sin lead, token o estado. Revisar manualmente antes de migrar';
  end if;
  if exists(select 1 from visitas where oportunidad_id is null or propiedad_id is null) then
    raise exception 'Hay visitas sin oportunidad o propiedad. No se reasignan automáticamente';
  end if;
  if exists(select 1 from oportunidades group by token_uuid having count(*)>1) then
    raise exception 'Hay tokens duplicados. No se reemplazan automáticamente';
  end if;
  if exists(select 1 from visitas group by oportunidad_id having count(*)>1) then
    raise exception 'Hay varias visitas para una oportunidad';
  end if;
  if exists(select 1 from oportunidades where resultado is null and fecha_cierre is null group by lead_id having count(*)>1) then
    raise exception 'Hay varias oportunidades abiertas por lead. Revisar cuáles deben mantenerse abiertas';
  end if;
end $$;

-- Relaciones faltantes e imágenes: se validan contra los registros existentes.
-- Solo se elimina la FK errónea de imágenes y las FK exactamente redundantes.
do $$
declare c record; canonical pg_constraint%rowtype;
begin
  if not exists(select 1 from pg_constraint where conrelid='public.visitas'::regclass and contype='f'
    and confrelid='public.oportunidades'::regclass
    and conkey=array[(select attnum from pg_attribute where attrelid='public.visitas'::regclass and attname='oportunidad_id')]::smallint[]) then
    alter table public.visitas add constraint visitas_oportunidad_id_fkey foreign key(oportunidad_id) references public.oportunidades(id);
  end if;
  if not exists(select 1 from pg_constraint where conrelid='public.oportunidades'::regclass and contype='f'
    and confrelid='public.leads'::regclass
    and conkey=array[(select attnum from pg_attribute where attrelid='public.oportunidades'::regclass and attname='lead_id')]::smallint[]) then
    alter table public.oportunidades add constraint oportunidades_lead_id_fkey foreign key(lead_id) references public.leads(id);
  end if;
  if not exists(select 1 from pg_constraint where conrelid='public.oportunidades'::regclass and contype='f'
    and confrelid='public.estado_oportunidad'::regclass
    and conkey=array[(select attnum from pg_attribute where attrelid='public.oportunidades'::regclass and attname='estado_id')]::smallint[]) then
    alter table public.oportunidades add constraint oportunidades_estado_id_fkey foreign key(estado_id) references public.estado_oportunidad(id);
  end if;
  for c in select conname from pg_constraint where conrelid='public.propiedad_imagenes'::regclass
    and contype='f' and confrelid='public.propiedades'::regclass
    and conkey=array[(select attnum from pg_attribute where attrelid='public.propiedad_imagenes'::regclass and attname='id')]::smallint[]
  loop
    execute format('alter table public.propiedad_imagenes drop constraint %I',c.conname);
  end loop;
  if not exists(select 1 from pg_constraint where conrelid='public.propiedad_imagenes'::regclass
    and contype='f' and confrelid='public.propiedades'::regclass
    and conkey=array[(select attnum from pg_attribute where attrelid='public.propiedad_imagenes'::regclass and attname='propiedad_id')]::smallint[]) then
    alter table public.propiedad_imagenes add constraint ru_imagen_propiedad_fk foreign key(propiedad_id) references public.propiedades(id);
  end if;
  -- El backend usa esta FK explícita para evitar el embedding ambiguo.
  if not exists(select 1 from pg_constraint where conrelid='public.visitas'::regclass and conname='visitas_propiedad_id_fkey') then
    alter table public.visitas add constraint visitas_propiedad_id_fkey foreign key(propiedad_id) references public.propiedades(id);
  end if;
  select * into canonical from pg_constraint where conrelid='public.visitas'::regclass and conname='visitas_propiedad_id_fkey';
  if canonical.contype<>'f' or canonical.confrelid<>'public.propiedades'::regclass
    or canonical.conkey<>array[(select attnum from pg_attribute where attrelid='public.visitas'::regclass and attname='propiedad_id')]::smallint[] then
    raise exception 'visitas_propiedad_id_fkey no corresponde a la relación esperada';
  end if;
  for c in select conname from pg_constraint where conrelid=canonical.conrelid and contype='f'
    and oid<>canonical.oid and confrelid=canonical.confrelid and conkey=canonical.conkey and confkey=canonical.confkey
    and confupdtype=canonical.confupdtype and confdeltype=canonical.confdeltype and confmatchtype=canonical.confmatchtype
    and condeferrable=canonical.condeferrable and condeferred=canonical.condeferred
  loop execute format('alter table public.visitas drop constraint %I',c.conname); end loop;
end $$;

alter table public.oportunidades alter column lead_id set not null;
alter table public.oportunidades alter column estado_id set not null;
alter table public.oportunidades alter column token_uuid set default gen_random_uuid();
alter table public.oportunidades alter column token_uuid set not null;
alter table public.visitas alter column oportunidad_id set not null;
alter table public.visitas alter column propiedad_id set not null;
create unique index if not exists ru_oportunidad_token_uq on public.oportunidades(token_uuid);
create unique index if not exists ru_oportunidad_abierta_por_lead_uq on public.oportunidades(lead_id) where resultado is null and fecha_cierre is null;
-- El esquema recibido ya tiene UNIQUE(oportunidad_id): no duplicar su índice.
do $$
begin
  if not exists(select 1 from pg_index where indrelid='public.visitas'::regclass
    and indisunique and indisvalid and indpred is null and indnkeyatts=1
    and indkey[0]=(select attnum from pg_attribute where attrelid='public.visitas'::regclass and attname='oportunidad_id')) then
    create unique index ru_visita_oportunidad_uq on public.visitas(oportunidad_id);
  end if;
end $$;
create index if not exists ru_oportunidad_lead_idx on public.oportunidades(lead_id,created_at);
create index if not exists ru_imagen_orden on public.propiedad_imagenes(propiedad_id,orden,id);
-- Metadatos técnicos de reintento; no se añaden campos comerciales del modelo viejo.
alter table public.visitas add column if not exists request_id uuid;
alter table public.visitas add column if not exists request_hash text;

create or replace function public.ru_solicitar_visita_oportunidad(
 p_token uuid,p_propiedad_id bigint,p_nombre text,p_fecha timestamptz,
 p_consentimiento boolean,p_request_id uuid,p_request_hash text,p_estado_nombre text,p_estado_oportunidad text
) returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare o public.oportunidades%rowtype; v public.visitas%rowtype;
 visit_state bigint; commercial_state bigint; state_count integer;
begin
  select * into o from public.oportunidades where token_uuid=p_token for update;
  if not found then raise exception 'RU_TOKEN'; end if;
  if o.resultado is not null or o.fecha_cierre is not null then raise exception 'RU_CLOSED'; end if;
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
end $$;

-- Para n8n: se crea una oportunidad únicamente al explorar. No se crea lead aquí.
create or replace function public.ru_obtener_o_crear_oportunidad(p_lead_id bigint)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare o public.oportunidades%rowtype; initial_state bigint; state_count integer;
begin
  perform id from public.leads where id=p_lead_id for update;
  if not found then raise exception 'RU_LEAD'; end if;
  select * into o from public.oportunidades where lead_id=p_lead_id and resultado is null and fecha_cierre is null;
  if found then return jsonb_build_object('id',o.id,'token_uuid',o.token_uuid,'estado_id',o.estado_id,'reutilizada',true); end if;
  select min(id),count(*) into initial_state,state_count from public.estado_oportunidad where nombre='nuevo';
  if state_count<>1 then raise exception 'RU_STATE: nuevo debe existir exactamente una vez'; end if;
  insert into public.oportunidades(lead_id,estado_id) values(p_lead_id,initial_state) returning * into o;
  return jsonb_build_object('id',o.id,'token_uuid',o.token_uuid,'estado_id',o.estado_id,'reutilizada',false);
end $$;

create or replace function public.ru_mis_visitas_oportunidades(p_token uuid,p_offset integer,p_limit integer,p_estado_pendiente text)
returns jsonb language plpgsql stable security definer set search_path=public,pg_temp as $$
declare access_op public.oportunidades%rowtype; result jsonb;
begin
  select * into access_op from public.oportunidades where token_uuid=p_token;
  if not found then raise exception 'RU_TOKEN'; end if;
  if access_op.resultado is not null or access_op.fecha_cierre is not null then raise exception 'RU_CLOSED'; end if;
  select coalesce(jsonb_agg(data order by priority,up_date,down_date desc,id),'[]'::jsonb) into result from (
    select v.id,
      case when coalesce(v.fecha_acordada,v.fecha_cliente)>=now() or s.nombre=p_estado_pendiente then 0 else 1 end priority,
      case when coalesce(v.fecha_acordada,v.fecha_cliente)>=now() or s.nombre=p_estado_pendiente then coalesce(v.fecha_acordada,v.fecha_cliente) end up_date,
      case when not(coalesce(v.fecha_acordada,v.fecha_cliente)>=now() or s.nombre=p_estado_pendiente) then coalesce(v.fecha_acordada,v.fecha_cliente) end down_date,
      jsonb_build_object('id',v.id,'oportunidad_id',o.id,'es_oportunidad_actual',o.id=access_op.id,
        'fecha_cliente',v.fecha_cliente,'fecha_agente',v.fecha_agente,'fecha_acordada',v.fecha_acordada,
        'estado_id',v.estado_id,'estados_visita',jsonb_build_object('nombre',s.nombre),
        'propiedades',jsonb_build_object('id',p.id,'titulo',p.titulo,
          'propiedad_imagenes',coalesce((select jsonb_agg(jsonb_build_object('id',i.id,'url',i.url,'orden',i.orden))
            from (select * from propiedad_imagenes where propiedad_id=p.id order by orden nulls last,id limit 1) i),'[]'::jsonb))) data
    from public.visitas v join public.oportunidades o on o.id=v.oportunidad_id
      left join public.propiedades p on p.id=v.propiedad_id left join public.estados_visita s on s.id=v.estado_id
    where o.lead_id=access_op.lead_id
    order by priority,up_date asc,down_date desc,v.id
    limit least(greatest(p_limit,1),60) offset greatest(p_offset,0)
  ) q;
  return result;
end $$;

-- Sin cambios de negocio: catálogo existente, incluyendo instalaciones que no
-- aplicaron la migración antigua (que ahora es incompatible).
create or replace function public.ru_filtros_propiedades() returns jsonb
language sql stable security definer set search_path=public,pg_temp as $$
 select jsonb_build_object(
  'operaciones',coalesce((select jsonb_agg(x order by x) from (select distinct tipo_operacion x from propiedades where disponible and tipo_operacion is not null) q),'[]'::jsonb),
  'tipos',coalesce((select jsonb_agg(x order by x) from (select distinct tipo_inmueble x from propiedades where disponible and tipo_inmueble is not null) q),'[]'::jsonb),
  'monedas',coalesce((select jsonb_agg(x order by x) from (select distinct moneda x from propiedades where disponible and moneda is not null) q),'[]'::jsonb),
  'distritos',coalesce((select jsonb_agg(jsonb_build_object('id',id,'nombre',nombre) order by nombre) from distritos d
    where exists(select 1 from propiedades p where p.disponible and p.distrito_id=d.id)),'[]'::jsonb)
 )
$$;

revoke all on function public.ru_solicitar_visita_oportunidad(uuid,bigint,text,timestamptz,boolean,uuid,text,text,text) from public,anon,authenticated;
revoke all on function public.ru_obtener_o_crear_oportunidad(bigint) from public,anon,authenticated;
revoke all on function public.ru_mis_visitas_oportunidades(uuid,integer,integer,text) from public,anon,authenticated;
revoke all on function public.ru_filtros_propiedades() from public,anon,authenticated;
grant execute on function public.ru_solicitar_visita_oportunidad(uuid,bigint,text,timestamptz,boolean,uuid,text,text,text) to service_role;
grant execute on function public.ru_obtener_o_crear_oportunidad(bigint) to service_role;
grant execute on function public.ru_mis_visitas_oportunidades(uuid,integer,integer,text) to service_role;
grant execute on function public.ru_filtros_propiedades() to service_role;
notify pgrst,'reload schema';
commit;
