import {el,dateText,fail,skeleton,finish} from './utils.js';
import {ApiError} from './api.js';
const token=decodeURIComponent(location.pathname.split('/')[2]||'');
const list=document.getElementById('agent-visits'),refresh=document.getElementById('refresh'),more=document.getElementById('more'),status=document.getElementById('status');
let offset=0,busy=false,valid=false;
async function request(path){
  const response=await fetch(`/api/agentes/${path}`,{headers:{'X-Agent-Token':token},cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(20000)});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new ApiError(typeof data.detail==='string'?data.detail:'No pudimos cargar las solicitudes.',response.status);
  return data;
}
function card(v){
  const p=v.propiedades||{},client=v.cliente||{};
  const phone=client.telefono||'';
  const contact=/^\+?[0-9 ()-]{7,25}$/.test(phone)?el('a',{href:`tel:${phone.replace(/[^+0-9]/g,'')}`},phone):phone||'No indicado';
  const details=[['Cliente',client.nombre||'Sin nombre'],['WhatsApp / teléfono',contact],['Fecha y hora preferida',dateText(v.fecha_cliente)],['Ubicación',[p.direccion,p.distritos?.nombre].filter(Boolean).join(' · ')||'No indicada'],['Tipo de inmueble',p.tipo_inmueble||'No indicado'],['Operación',p.tipo_operacion||'No indicada']];
  if(v.fecha_agente)details.push(['Fecha propuesta por el agente',dateText(v.fecha_agente)]);
  if(v.fecha_acordada)details.push(['Fecha acordada',dateText(v.fecha_acordada)]);
  return el('article',{class:'card agent-visit'},el('span',{class:'pill'},v.estados_visita?.nombre||'Solicitada'),el('h2',{},p.titulo||'Inmueble solicitado'),el('span',{class:'muted'},`Solicitud #${v.id}`),el('dl',{},details.map(([label,value])=>el('div',{},el('dt',{},label),el('dd',{},value)))));
}
async function load(append=false){
  if(busy)return;busy=true;refresh.disabled=true;more.disabled=true;
  if(!append){offset=0;skeleton(list,2);more.hidden=true;}
  try{
    const context=await request('contexto');valid=true;
    document.getElementById('agent-context').textContent=`${context.nombre||'Agente'} · ${context.especialidad}`;
    const rows=await request(`visitas?offset=${offset}&limit=20`);
    if(!append)list.replaceChildren();
    rows.forEach(v=>list.append(card(v)));offset+=rows.length;
    if(!offset)list.append(el('div',{class:'state'},el('h2',{},'Sin solicitudes pendientes'),el('p',{},'No hay visitas solicitadas para tu especialidad.')));
    more.hidden=rows.length<20;status.textContent=`${offset} solicitud(es) mostrada(s).`;
  }catch(error){
    if([401,403,404].includes(error.status)){valid=false;list.replaceChildren();more.hidden=true;document.getElementById('agent-context').textContent='Acceso no disponible';}
    if(append&&valid)status.textContent=error.message||'No pudimos conectar. Intenta actualizar.';
    else fail(list,error,()=>load());
  }finally{busy=false;finish(list);refresh.disabled=!valid;more.disabled=false;}
}
refresh.addEventListener('click',()=>load());more.addEventListener('click',()=>load(true));load();
