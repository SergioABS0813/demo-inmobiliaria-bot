-- NO aplicada automáticamente. Requiere revisar 00_diagnostico.sql y README.
-- Contrato: IDs enteros, fecha_cliente/agente/acordada y consentimiento_at
-- timestamptz, token_uuid UUID, nombre de visita = código visible de solicitud.
-- No crea entidades alternativas, estados ni leads. Ejecutar como propietario.
begin;

do $$
declare r record;
begin
  for r in select * from (values
    ('leads','id','integer'), ('propiedades','id','integer'), ('visitas','id','integer'),
    ('visitas','lead_id','integer'), ('visitas','propiedad_id','integer'),
    ('propiedad_imagenes','propiedad_id','integer'),
    ('leads','token_uuid','uuid'), ('visitas','fecha_cliente','timestamp with time zone'),
    ('visitas','fecha_agente','timestamp with time zone'), ('visitas','fecha_acordada','timestamp with time zone'),
    ('leads','consentimiento_at','timestamp with time zone')
  ) as expected(t,c,kind)
  loop
    if not exists(select 1 from information_schema.columns where table_schema='public'
      and table_name=r.t and column_name=r.c and
      (data_type=r.kind or (r.kind='integer' and data_type in ('smallint','bigint')))) then
      raise exception 'Contrato incompatible: %.% debe ser %; revisar diagnóstico antes de adaptar migración', r.t,r.c,r.kind;
    end if;
  end loop;
  if not exists(select 1 from information_schema.columns where table_schema='public' and table_name='visitas'
    and column_name='id' and (column_default is not null or is_identity='YES')) then
    raise exception 'visitas.id necesita identity o secuencia existente';
  end if;
end $$;

-- Corrige exclusivamente la FK errónea id -> propiedades.id descrita en el brief.
-- No elimina otras relaciones del esquema.
do $$
declare bad record;
begin
  for bad in select c.conname from pg_constraint c
    join pg_attribute a on a.attrelid=c.conrelid and a.attnum=c.conkey[1]
    where c.contype='f' and c.conrelid='public.propiedad_imagenes'::regclass
    and c.confrelid='public.propiedades'::regclass and cardinality(c.conkey)=1 and a.attname='id'
  loop
    execute format('alter table public.propiedad_imagenes drop constraint %I',bad.conname);
  end loop;
  if not exists(select 1 from pg_constraint c join pg_attribute a on a.attrelid=c.conrelid and a.attnum=c.conkey[1]
    where c.contype='f' and c.conrelid='public.propiedad_imagenes'::regclass
    and c.confrelid='public.propiedades'::regclass and cardinality(c.conkey)=1 and a.attname='propiedad_id') then
    alter table public.propiedad_imagenes add constraint ru_imagen_propiedad_fk
      foreign key(propiedad_id) references public.propiedades(id);
  end if;
end $$;

create unique index if not exists ru_lead_token_uq on public.leads(token_uuid);
alter table public.visitas add column if not exists request_id uuid;
alter table public.visitas add column if not exists request_hash text;
create unique index if not exists ru_visita_request_uq on public.visitas(lead_id,request_id);
create index if not exists ru_visita_lead_fecha on public.visitas(lead_id,fecha_cliente);
create index if not exists ru_imagen_orden on public.propiedad_imagenes(propiedad_id,orden,id);

create or replace function public.ru_solicitar_visita(
 p_token uuid,p_propiedad_id bigint,p_nombre text,p_fecha timestamptz,
 p_consentimiento boolean,p_request_id uuid,p_request_hash text,p_estado_nombre text
) returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare l public.leads%rowtype; v public.visitas%rowtype; s bigint; state_count int;
begin
  select * into l from public.leads where token_uuid=p_token for update;
  if not found then raise exception 'RU_TOKEN'; end if;
  -- Serializa solicitudes del mismo lead y comprueba replay ANTES de fecha/disponibilidad.
  select * into v from public.visitas where lead_id=l.id and request_id=p_request_id;
  if found then
    if v.request_hash is distinct from p_request_hash then raise exception 'RU_REPLAY'; end if;
    return jsonb_build_object('id',v.id,'nombre',v.nombre,'replayed',true);
  end if;
  if p_request_id is null or p_request_hash is null or length(p_request_hash)<>64 then raise exception 'RU_REPLAY'; end if;
  if p_consentimiento is distinct from true then raise exception 'RU_CONSENT'; end if;
  if p_fecha is null or p_fecha<=clock_timestamp() then raise exception 'RU_DATE'; end if;
  if p_nombre is null or length(trim(p_nombre))<3 or length(trim(p_nombre))>120 then raise exception 'RU_NAME'; end if;
  perform id from public.propiedades where id=p_propiedad_id and disponible=true for share;
  if not found then raise exception 'RU_UNAVAILABLE'; end if;
  select min(id),count(*) into s,state_count from public.estados_visita where nombre=p_estado_nombre;
  if state_count<>1 then raise exception 'RU_STATE: debe existir exactamente un estado inicial con el nombre configurado'; end if;
  update public.leads set nombre=trim(p_nombre),consentimiento=true,
    consentimiento_at=case when consentimiento=true and consentimiento_at is not null then consentimiento_at else clock_timestamp() end,
    updated_at=clock_timestamp() where id=l.id;
  insert into public.visitas(nombre,lead_id,propiedad_id,fecha_cliente,estado_id,request_id,request_hash)
    values('Solicitud',l.id,p_propiedad_id,p_fecha,s,p_request_id,p_request_hash) returning * into v;
  update public.visitas set nombre='VIS-'||lpad(v.id::text,greatest(6,length(v.id::text)),'0') where id=v.id returning * into v;
  -- fecha_agente y fecha_acordada deben tener DEFAULT NULL en el esquema existente.
  if v.fecha_agente is not null or v.fecha_acordada is not null then
    raise exception 'Defaults incompatibles: una solicitud no puede nacer confirmada';
  end if;
  return jsonb_build_object('id',v.id,'nombre',v.nombre,'replayed',false);
end $$;

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

create or replace function public.ru_mis_visitas(p_lead_id bigint,p_offset integer,p_limit integer,p_estado_pendiente text)
returns jsonb language sql stable security definer set search_path=public,pg_temp as $$
 select coalesce(jsonb_agg(data order by priority,up_date,down_date,id),'[]'::jsonb) from (
  select v.id,
   case when coalesce(v.fecha_acordada,v.fecha_cliente)>=now() or s.nombre=p_estado_pendiente then 0 else 1 end priority,
   case when coalesce(v.fecha_acordada,v.fecha_cliente)>=now() or s.nombre=p_estado_pendiente then coalesce(v.fecha_acordada,v.fecha_cliente) end up_date,
   case when not(coalesce(v.fecha_acordada,v.fecha_cliente)>=now() or s.nombre=p_estado_pendiente) then coalesce(v.fecha_acordada,v.fecha_cliente) end down_date,
   jsonb_build_object('id',v.id,'nombre',v.nombre,'fecha_cliente',v.fecha_cliente,'fecha_acordada',v.fecha_acordada,
     'motivo',v.motivo,'estados_visita',jsonb_build_object('nombre',s.nombre),
     'propiedades',jsonb_build_object('id',p.id,'titulo',p.titulo,
       'propiedad_imagenes',coalesce((select jsonb_agg(jsonb_build_object('id',i.id,'url',i.url,'orden',i.orden) order by i.orden nulls last,i.id)
         from (select * from propiedad_imagenes where propiedad_id=p.id order by orden nulls last,id limit 1) i),'[]'::jsonb))) data
  from visitas v join propiedades p on p.id=v.propiedad_id join estados_visita s on s.id=v.estado_id
  where v.lead_id=p_lead_id
  order by priority,up_date asc,down_date desc,v.id limit least(greatest(p_limit,1),60) offset greatest(p_offset,0)
 ) q
$$;

-- RPCs privilegiadas accesibles solamente al backend con service_role.
revoke all on function public.ru_solicitar_visita(uuid,bigint,text,timestamptz,boolean,uuid,text,text) from public,anon,authenticated;
revoke all on function public.ru_filtros_propiedades() from public,anon,authenticated;
revoke all on function public.ru_mis_visitas(bigint,integer,integer,text) from public,anon,authenticated;
grant execute on function public.ru_solicitar_visita(uuid,bigint,text,timestamptz,boolean,uuid,text,text) to service_role;
grant execute on function public.ru_filtros_propiedades() to service_role;
grant execute on function public.ru_mis_visitas(bigint,integer,integer,text) to service_role;
commit;
