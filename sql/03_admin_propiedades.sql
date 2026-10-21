-- Migración MANUAL y aditiva. No modifica leads/oportunidades/visitas ni borra datos.
-- Ejecutar sobre el esquema vigente con las FK corregidas.
begin;
alter table public.propiedad_imagenes add column if not exists categoria text;
do $$ begin
  if not exists(select 1 from pg_constraint where conrelid='public.propiedad_imagenes'::regclass and conname='ru_imagen_categoria_check') then
    alter table public.propiedad_imagenes add constraint ru_imagen_categoria_check
      check(categoria is null or categoria in ('vista_1','vista_2','plano'));
  end if;
end $$;
-- Clasificar solo cuando la URL existente identifica inequívocamente la carpeta.
-- Las demás imágenes conservan categoria NULL y se muestran como "Sin clasificar".
update public.propiedad_imagenes set categoria=substring(url from '/propiedad_[0-9]+/(vista_1|vista_2|plano)/')
where categoria is null and url ~ '/propiedad_[0-9]+/(vista_1|vista_2|plano)/';

-- Outbox técnico: eliminar la fila y registrar el archivo por limpiar es atómico.
-- Supabase Storage no comparte transacción con PostgreSQL. No es un módulo CRM.
create table if not exists public.propiedad_archivos_pendientes (
  id bigint generated always as identity primary key,
  bucket text not null check(bucket='imagenes-inmobiliaria-demo'),
  object_key text not null check(object_key ~ '^propiedad_[0-9]+/(vista_1|vista_2|plano)/[a-zA-Z0-9_.-]+$' and position('..' in object_key)=0),
  created_at timestamptz not null default now(),
  unique(bucket,object_key)
);
alter table public.propiedad_archivos_pendientes enable row level security;
revoke all on public.propiedad_archivos_pendientes from public,anon,authenticated;
grant select,insert,update,delete on public.propiedad_archivos_pendientes to service_role;
grant usage,select on sequence public.propiedad_archivos_pendientes_id_seq to service_role;

create or replace function public.ru_admin_registrar_imagen(p_propiedad_id bigint,p_url text,p_categoria text)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare image public.propiedad_imagenes%rowtype; next_order bigint;
begin
  perform id from public.propiedades where id=p_propiedad_id for update;
  if not found then raise exception 'RU_ADMIN_PROPERTY'; end if;
  if p_categoria is null or p_categoria not in ('vista_1','vista_2','plano') then raise exception 'RU_ADMIN_IMAGE'; end if;
  select coalesce(max(orden),0)+1 into next_order from public.propiedad_imagenes where propiedad_id=p_propiedad_id;
  insert into public.propiedad_imagenes(propiedad_id,url,orden,categoria)
    values(p_propiedad_id,p_url,next_order,p_categoria) returning * into image;
  return to_jsonb(image);
end $$;

create or replace function public.ru_admin_ordenar_imagenes(p_propiedad_id bigint,p_ids bigint[])
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare image_count integer; unique_count integer; result jsonb;
begin
  perform id from public.propiedades where id=p_propiedad_id for update;
  if not found then raise exception 'RU_ADMIN_PROPERTY'; end if;
  select count(*) into image_count from public.propiedad_imagenes where propiedad_id=p_propiedad_id;
  select count(distinct x) into unique_count from unnest(p_ids) x;
  if p_ids is null or cardinality(p_ids)<>image_count or unique_count<>image_count
     or exists(select 1 from unnest(p_ids) x where not exists(select 1 from public.propiedad_imagenes where id=x and propiedad_id=p_propiedad_id)) then
    raise exception 'RU_ADMIN_ORDER';
  end if;
  update public.propiedad_imagenes i set orden=t.n
    from unnest(p_ids) with ordinality as t(id,n) where i.id=t.id and i.propiedad_id=p_propiedad_id;
  select coalesce(jsonb_agg(to_jsonb(i) order by i.orden,i.id),'[]'::jsonb) into result
    from public.propiedad_imagenes i where propiedad_id=p_propiedad_id;
  return result;
end $$;

create or replace function public.ru_admin_retirar_imagen(p_propiedad_id bigint,p_imagen_id bigint,p_url_esperada text,p_bucket text,p_object_key text)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare image public.propiedad_imagenes%rowtype;
begin
  perform id from public.propiedades where id=p_propiedad_id for update;
  if not found then raise exception 'RU_ADMIN_PROPERTY'; end if;
  select * into image from public.propiedad_imagenes where id=p_imagen_id and propiedad_id=p_propiedad_id for update;
  if not found then raise exception 'RU_ADMIN_IMAGE'; end if;
  if image.url is distinct from p_url_esperada then raise exception 'RU_ADMIN_ORDER'; end if;
  if p_object_key is not null then
    if p_bucket is distinct from 'imagenes-inmobiliaria-demo'
      or p_object_key !~ ('^propiedad_'||p_propiedad_id||'/(vista_1|vista_2|plano)/[a-zA-Z0-9_.-]+$') then
      raise exception 'RU_ADMIN_IMAGE';
    end if;
    insert into public.propiedad_archivos_pendientes(bucket,object_key) values(p_bucket,p_object_key)
      on conflict(bucket,object_key) do nothing;
  end if;
  delete from public.propiedad_imagenes where id=image.id;
  return jsonb_build_object('eliminada',true);
end $$;

revoke all on function public.ru_admin_registrar_imagen(bigint,text,text) from public,anon,authenticated;
revoke all on function public.ru_admin_ordenar_imagenes(bigint,bigint[]) from public,anon,authenticated;
revoke all on function public.ru_admin_retirar_imagen(bigint,bigint,text,text,text) from public,anon,authenticated;
grant execute on function public.ru_admin_registrar_imagen(bigint,text,text) to service_role;
grant execute on function public.ru_admin_ordenar_imagenes(bigint,bigint[]) to service_role;
grant execute on function public.ru_admin_retirar_imagen(bigint,bigint,text,text,text) to service_role;
notify pgrst,'reload schema';
commit;
