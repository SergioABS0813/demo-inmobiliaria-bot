import {el,dateText,fail,skeleton,finish} from './utils.js';
import {ApiError} from './api.js';
import {normalizePhone} from './agent-phone.js';
const token=decodeURIComponent(location.pathname.split('/')[2]||'');
const list=document.getElementById('agent-visits'),refresh=document.getElementById('refresh'),more=document.getElementById('more'),status=document.getElementById('status');
let offset=0,busy=false,valid=false,view='pendientes',updating=false;
const pendingTab=document.getElementById('pending-tab'),contactedTab=document.getElementById('contacted-tab'),feedback=document.getElementById('feedback');
function notify(message,isError=false){feedback.textContent=message;feedback.className=isError?'error':'notice';feedback.setAttribute('role',isError?'alert':'status');feedback.hidden=false;}
async function updateCounts(){try{const data=await request('visitas/conteos');pendingTab.textContent=`Pendientes (${data.pendientes})`;contactedTab.textContent=`Contactadas (${data.contactadas})`;}catch{status.textContent+=' No pudimos actualizar los contadores.';}}
function setView(next){if(busy||updating)return;view=next;pendingTab.setAttribute('aria-pressed',String(view==='pendientes'));contactedTab.setAttribute('aria-pressed',String(view==='contactadas'));feedback.hidden=true;load();}
pendingTab.addEventListener('click',()=>setView('pendientes'));contactedTab.addEventListener('click',()=>setView('contactadas'));
async function markContacted(v,button){
  if(updating||busy)return;
  if(!window.confirm('¿Ya contactaste al cliente? La solicitud pasará a Contactadas sin confirmar ni cambiar las fechas.'))return;
  updating=true;button.disabled=true;button.classList.add('is-loading');button.textContent='Guardando…';
  let saved=false;
  try{await request(`visitas/${v.id}/contactar`,{method:'POST'});saved=true;notify('Solicitud marcada como contactada.');await load(false,true);}
  catch(error){notify(error.message||'No pudimos guardar el cambio. Intenta nuevamente.',true);if(error.status===409)await load(false,true);}
  finally{updating=false;if(!saved){button.disabled=false;button.classList.remove('is-loading');button.textContent='Marcar como contactado';}}
}
async function request(path,{method='GET'}={}){
  const response=await fetch(`/api/agentes/${path}`,{method,headers:{'X-Agent-Token':token},cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(20000)});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new ApiError(typeof data.detail==='string'?data.detail:'No pudimos cargar las solicitudes.',response.status);
  return data;
}
function card(v){
  const p=v.propiedades||{},client=v.cliente||{};
  const phone=client.telefono||'';
  const normalized=normalizePhone(phone);
  const contact=phone||'No indicado';
  const details=[['Cliente',client.nombre||'Sin nombre'],['WhatsApp / teléfono',contact],['Fecha y hora preferida',dateText(v.fecha_cliente)],['Ubicación',[p.direccion,p.distritos?.nombre].filter(Boolean).join(' · ')||'No indicada'],['Tipo de inmueble',p.tipo_inmueble||'No indicado'],['Operación',p.tipo_operacion||'No indicada']];
  if(v.fecha_agente)details.push(['Fecha propuesta por el agente',dateText(v.fecha_agente)]);
  if(v.fecha_acordada)details.push(['Fecha acordada',dateText(v.fecha_acordada)]);
  const actions=el('div',{class:'agent-actions'});
  if(normalized){
    actions.append(el('a',{class:'btn secondary',href:`tel:${normalized.tel}`},el('span',{'aria-hidden':'true'},'☎'),'Llamar'));
    const message=`Hola, ${client.nombre||'¿cómo estás?'}. Soy asesor inmobiliario de Raíz Urbana. Me comunico contigo por tu solicitud de visita a ${p.titulo||'este inmueble'}. ¿Podemos coordinar los detalles?`;
    const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');
    for(const [key,value] of Object.entries({viewBox:'0 0 24 24',width:'18',height:'18','aria-hidden':'true'}))icon.setAttribute(key,value);
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('fill','currentColor');path.setAttribute('d','M12 2a10 10 0 0 0-8.7 15L2 22l5.1-1.3A10 10 0 1 0 12 2Zm0 2a8 8 0 1 1-4.6 14.5l-.4-.2-2.2.6.6-2.1-.3-.4A8 8 0 0 1 12 4Zm-3 3c-.6 0-1.5.7-1.5 2s1 3 2.4 4.4c1.4 1.4 3.1 2.2 4.4 2.2 1.2 0 2-.8 2-1.4l-2.2-1.1-.8 1c-1.6-.6-2.7-1.7-3.3-3.2l1-.8L10 7Z');icon.append(path);
    actions.append(el('a',{class:'btn secondary',href:`https://wa.me/${normalized.whatsapp}?text=${encodeURIComponent(message)}`,target:'_blank',rel:'noopener noreferrer'},icon,'WhatsApp'));
  }else{
    const call=el('button',{class:'btn secondary',type:'button'},'☎ Llamar'),wa=el('button',{class:'btn secondary',type:'button'},'WhatsApp');call.disabled=true;wa.disabled=true;
    actions.append(call,wa,el('small',{class:'muted'},'Sin teléfono válido para contactar.'));
  }
  if(view==='pendientes'){
    const button=el('button',{class:'btn teal',type:'button'},'Marcar como contactado');button.addEventListener('click',()=>markContacted(v,button));actions.append(button);
  }
  return el('article',{class:'card agent-visit'},el('span',{class:'pill'},v.estados_visita?.nombre||'Solicitada'),el('h2',{},p.titulo||'Inmueble solicitado'),el('span',{class:'muted'},`Solicitud #${v.id}`),el('dl',{},details.map(([label,value])=>el('div',{},el('dt',{},label),el('dd',{},value)))),actions);
}
async function load(append=false,afterMutation=false){
  if(busy||(updating&&!afterMutation))return;busy=true;refresh.disabled=true;more.disabled=true;
  if(!append){offset=0;skeleton(list,2);more.hidden=true;}
  try{
    const context=await request('contexto');valid=true;
    document.getElementById('agent-context').textContent=`${context.nombre||'Agente'} · ${context.especialidad}`;
    const rows=await request(`visitas?estado=${view}&offset=${offset}&limit=20`);
    if(!append)list.replaceChildren();
    rows.forEach(v=>list.append(card(v)));offset+=rows.length;
    if(!offset)list.append(el('div',{class:'state'},el('h2',{},view==='pendientes'?'Sin solicitudes pendientes':'Sin solicitudes contactadas'),el('p',{},'No hay solicitudes en esta vista para tu especialidad.')));
    more.hidden=rows.length<20;status.textContent=`${offset} solicitud(es) mostrada(s).`;await updateCounts();
  }catch(error){
    if([401,403,404].includes(error.status)){valid=false;list.replaceChildren();more.hidden=true;document.getElementById('agent-context').textContent='Acceso no disponible';}
    if(append&&valid)status.textContent=error.message||'No pudimos conectar. Intenta actualizar.';
    else fail(list,error,()=>load());
  }finally{busy=false;finish(list);refresh.disabled=!valid;more.disabled=false;}
}
refresh.addEventListener('click',()=>load());more.addEventListener('click',()=>load(true));load();
