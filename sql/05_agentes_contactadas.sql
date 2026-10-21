-- Estado y transicion explicita. No altera relaciones ni registros historicos.
begin;
lock table public.estados_visita in share row exclusive mode;
insert into public.estados_visita(nombre)
select 'contactada' where not exists (select 1 from public.estados_visita where nombre='contactada');

create or replace function public.ru_agente_contactar_visita(p_token uuid,p_visita_id bigint,p_estado_pendiente text)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare a public.agentes%rowtype; v public.visitas%rowtype;
  specialty text; current_name text; target_id bigint; matches integer;
begin
  select count(*) into matches from public.agentes where token_uuid=p_token;
  if matches<>1 then raise exception 'RU_AGENT_ACCESS'; end if;
  select * into a from public.agentes where token_uuid=p_token for share;
  if a.especialidad is null or trim(a.especialidad)='' then raise exception 'RU_AGENT_ACCESS'; end if;
  select * into v from public.visitas where id=p_visita_id for update;
  if not found then raise exception 'RU_AGENT_VISIT'; end if;
  select tipo_inmueble into specialty from public.propiedades where id=v.propiedad_id for share;
  if specialty is distinct from a.especialidad then raise exception 'RU_AGENT_VISIT'; end if;
  select nombre into current_name from public.estados_visita where id=v.estado_id for share;
  if current_name='contactada' then raise exception 'RU_AGENT_CONTACTED'; end if;
  if current_name is distinct from p_estado_pendiente then raise exception 'RU_AGENT_PENDING'; end if;
  perform id from public.oportunidades where id=v.oportunidad_id and resultado is null and fecha_cierre is null for share;
  if not found then raise exception 'RU_AGENT_PENDING'; end if;
  select min(id),count(*) into target_id,matches from public.estados_visita where nombre='contactada';
  if matches<>1 then raise exception 'RU_AGENT_STATE'; end if;
  update public.visitas set estado_id=target_id,updated_at=clock_timestamp() where id=v.id;
  return jsonb_build_object('id',v.id,'estado','contactada');
end $$;
revoke all on function public.ru_agente_contactar_visita(uuid,bigint,text) from public,anon,authenticated;
grant execute on function public.ru_agente_contactar_visita(uuid,bigint,text) to service_role;
notify pgrst,'reload schema';
commit;
