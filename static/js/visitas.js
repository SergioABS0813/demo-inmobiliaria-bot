import {api,base} from './api.js';
import {el,shell,photo,images,dateText,fail,skeleton,finish} from './utils.js';
const isConfirmation=location.pathname.includes('/confirmacion/');shell('visitas');
const container=document.getElementById('visits');
let offset=0,revision=0,controller;
function visitCard(v){
  const property=v.propiedades;
  const body=el('div',{class:'visit-body'},el('span',{class:'pill'},v.estados_visita?.nombre || 'Estado no indicado'),
    el('h2',{},property?.titulo || 'Propiedad no disponible'),el('p',{class:'muted'},`Solicitud #${v.id}${v.es_oportunidad_actual?' · Oportunidad actual':''}`),
    el('p',{},el('strong',{},'Fecha solicitada: '),dateText(v.fecha_cliente)));
  if(v.fecha_acordada)body.append(el('p',{},el('strong',{},'Fecha acordada: '),dateText(v.fecha_acordada)));
  else body.append(el('p',{class:'muted'},'La fecha definitiva todavía requiere coordinación.'));
  if(property)body.append(el('a',{class:'btn text',href:`${base}/propiedad/${property.id}`},'Ver inmueble ↗'));
  return el('article',{class:'card visit'},photo(images(property||{})[0]?.url,property?.titulo||'Inmueble solicitado'),body);
}
async function load(append=false){
  controller?.abort();controller=new AbortController();const current=++revision;
  const more=document.getElementById('more');if(more)more.disabled=true;
  if(!append){offset=0;skeleton(container,2);}
  try{
    if(isConfirmation){
      const id=Number(location.pathname.split('/').pop()),v=await api(`/visitas/${id}`,{signal:controller.signal});
      if(current!==revision)return;
      const pending=!v.fecha_acordada;
      const content=el('section',{class:'card confirmation'},el('div',{class:'success-mark','aria-hidden':'true'},'✓'),
        el('span',{class:'eyebrow'},`Solicitud #${v.id}`),el('h1',{},'Hemos recibido tu solicitud'),
        el('p',{class:'muted'},'Gracias por dar el siguiente paso. Consulta aquí la información actual de tu solicitud.'),
        el('div',{class:'summary'},el('h2',{},v.propiedades?.titulo||'Inmueble solicitado'),
          el('p',{},'Fecha solicitada: ',el('strong',{},dateText(v.fecha_cliente))),
          el('p',{},'Hora de Lima, Perú'),el('span',{class:'pill'},v.estados_visita?.nombre||'Estado no indicado')),
        el('p',{class:'notice'},pending?'La fecha solicitada no implica una reserva confirmada. Revisa el estado actual y coordina los detalles con tu asesor por WhatsApp.':`Fecha acordada: ${dateText(v.fecha_acordada)}.`),
        el('div',{class:'actions'},el('a',{class:'btn teal',href:`${base}/mis-visitas`},'Consultar mis visitas'),el('a',{class:'btn secondary',href:base},'Seguir explorando')));
      container.replaceChildren(content);
    }else{
      const rows=await api(`/visitas/mias?offset=${offset}&limit=20`,{signal:controller.signal});
      if(current!==revision)return;
      if(!append)container.replaceChildren();
      rows.forEach(v=>container.append(visitCard(v)));offset+=rows.length;
      if(!offset){container.replaceChildren(el('div',{class:'state'},el('h2',{},'Tu próximo hogar empieza con una visita'),el('p',{},'Todavía no tienes solicitudes. Explora los inmuebles y elige el espacio que te gustaría conocer.'),el('a',{class:'btn teal',href:base},'Explorar inmuebles')));}
      more.hidden=rows.length<20;
      document.getElementById('refresh-status').textContent=`Información actualizada a las ${new Intl.DateTimeFormat('es-PE',{timeZone:'America/Lima',hour:'2-digit',minute:'2-digit'}).format(new Date())}`;
    }
  }catch(error){
    if(error.name==='AbortError'||current!==revision)return;
    if(append){document.getElementById('refresh-status').textContent=error.message;}
    else fail(container,error,()=>load());
  }finally{if(current===revision){finish(container);if(more)more.disabled=false;}}
}
document.getElementById('refresh')?.addEventListener('click',()=>load());
document.getElementById('more')?.addEventListener('click',()=>load(true));load();
