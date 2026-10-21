-- Aplicar despues de 02_oportunidades.sql. No elimina datos.
begin;
create or replace function public.ru_solicitar_visita_contacto(
 p_token uuid,p_propiedad_id bigint,p_nombre text,p_fecha timestamptz,
 p_consentimiento boolean,p_request_id uuid,p_request_hash text,p_estado_nombre text,p_estado_oportunidad text,p_telefono text
) returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare result jsonb; lead bigint;
begin
  if p_telefono is null or p_telefono !~ '^\+?[0-9]{7,15}$' then
    raise exception 'Telefono de WhatsApp invalido';
  end if;
  -- El bloqueo se mantiene durante la solicitud y el cambio de contacto.
  select lead_id into lead from public.oportunidades where token_uuid=p_token for update;
  result := public.ru_solicitar_visita_oportunidad(p_token,p_propiedad_id,p_nombre,p_fecha,
    p_consentimiento,p_request_id,p_request_hash,p_estado_nombre,p_estado_oportunidad);
  if not (result->>'replayed')::boolean then
    update public.leads set telefono=p_telefono where id=lead;
  end if;
  -- Si el telefono viola UNIQUE, toda la transaccion se revierte.
  return result;
end $$;
revoke all on function public.ru_solicitar_visita_contacto(uuid,bigint,text,timestamptz,boolean,uuid,text,text,text,text) from public,anon,authenticated;
grant execute on function public.ru_solicitar_visita_contacto(uuid,bigint,text,timestamptz,boolean,uuid,text,text,text,text) to service_role;
notify pgrst,'reload schema';
commit;
