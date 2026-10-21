import {api,base,propertyId} from './api.js';
import {el,shell,photo,images,money,fail,finish,existingVisit} from './utils.js';
shell();
const form=document.getElementById('request-form'),panel=document.getElementById('property-summary');
const error=document.getElementById('form-error'),fields=document.getElementById('request-fields'),submit=document.getElementById('submit');
let sending=false, lastPayload=null, requestId=null, selectedProperty=null, reviewedPayload=null;
const review=document.getElementById('visit-review'),confirm=document.getElementById('confirm-request'),edit=document.getElementById('edit-request');
function editRequest(){review.hidden=true;fields.hidden=false;reviewedPayload=null;}
edit.addEventListener('click',()=>{if(sending)return;editRequest();form.elements.nombre.focus();});
const storageKey=`ru-request:${propertyId}`;
function todayLima(){return new Intl.DateTimeFormat('en-CA',{timeZone:'America/Lima',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
async function load(){
  try{
    const [p,context]=await Promise.all([api(`/propiedades/${propertyId}`),api('/lead/contexto')]);
    if(context.visita_id){existingVisit(form,context.visita_id);panel.hidden=true;return;}
    if(!p.disponible){form.hidden=true;panel.replaceChildren(el('p',{class:'error'},'Esta propiedad ya no está disponible para nuevas visitas.'));return;}
    selectedProperty=p;
    panel.replaceChildren(photo(images(p)[0]?.url,p.titulo,{lazy:false}),el('div',{},el('span',{class:'pill'},p.tipo_operacion),el('h2',{},p.titulo),el('p',{class:'muted'},p.distrito),el('strong',{class:'detail-price'},money(p.precio,p.moneda))));
    form.elements.nombre.value=context.nombre||'';
    form.elements.telefono.value=context.telefono||'';
    document.getElementById('privacy-contact').textContent=context.privacy_contact?`Para consultas sobre tus datos: ${context.privacy_contact}.`:'Esta demo no debe recibir datos reales hasta que la inmobiliaria configure su contacto de privacidad.';
    form.elements.fecha.min=todayLima();fields.disabled=false;
    // The acknowledgement is request-only; the new leads schema has no consent columns.
  }catch(err){form.hidden=true;fail(panel,err,()=>{form.hidden=false;load();});}finally{finish(panel);}
}
function showError(text){editRequest();error.textContent=text;error.hidden=false;error.focus();}
form.addEventListener('submit',async event=>{
  event.preventDefault();if(sending)return;
  const data=new FormData(form);
  const date=`${data.get('fecha')}T${data.get('hora')}:00-05:00`;
  if(!Number.isFinite(Date.parse(date))||Date.parse(date)<=Date.now()){showError('Elige una fecha y hora futuras en Lima.');form.elements.fecha.focus();return;}
  const payload={propiedad_id:propertyId,nombre:String(data.get('nombre')).trim(),telefono:String(data.get('telefono')).trim(),fecha_cliente:date,consentimiento:data.get('consentimiento')==='on'};
  if(payload.nombre.length<3||!/[\p{L}]/u.test(payload.nombre)){showError('Indica tu nombre completo.');return;}
  const serialized=JSON.stringify(payload);
  if(event.submitter!==confirm||reviewedPayload!==serialized){
    const when=new Date(date);
    const day=new Intl.DateTimeFormat('es-PE',{weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'America/Lima'}).format(when);
    const hour=new Intl.DateTimeFormat('es-PE',{hour:'numeric',minute:'2-digit',timeZone:'America/Lima'}).format(when);
    const details=[['Nombre',payload.nombre],['Teléfono',form.elements.telefono.value||'No disponible'],['Fecha preferida',day],['Hora preferida',`${hour} (Lima, Perú)`],['Propiedad',selectedProperty.titulo||'Inmueble seleccionado'],['Ubicación',[selectedProperty.direccion,selectedProperty.distrito].filter(Boolean).join(' · ')||'Por coordinar con el asesor']];
    document.getElementById('review-details').replaceChildren(...details.flatMap(([label,value])=>[el('dt',{},label),el('dd',{},value)]));
    reviewedPayload=serialized;error.hidden=true;fields.hidden=true;review.hidden=false;
    document.getElementById('review-title').focus();return;
  }
  confirm.disabled=true;edit.disabled=true;confirm.textContent='Enviando solicitud…';
  sending=true;fields.disabled=true;submit.textContent='Enviando solicitud…';error.hidden=true;
  // Only the payload digest + random key are stored, never name, token or dates.
  let digest;
  try{
    digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(serialized)))).map(b=>b.toString(16).padStart(2,'0')).join('');
  }catch{showError('Abre esta página mediante HTTPS o localhost para enviar la solicitud de forma segura.');sending=false;fields.disabled=false;submit.textContent='Revisar solicitud';confirm.disabled=false;edit.disabled=false;confirm.textContent='Confirmar y enviar solicitud';return;}
  if(lastPayload!==digest){
    let previous;try{previous=JSON.parse(sessionStorage.getItem(storageKey)||'null');}catch{}
    requestId=previous?.digest===digest?previous.requestId:crypto.randomUUID();lastPayload=digest;
    try{sessionStorage.setItem(storageKey,JSON.stringify({digest,requestId}));}catch{}
  }
  try{
    const result=await api('/visitas',{method:'POST',body:{...payload,request_id:requestId}});
    try{sessionStorage.removeItem(storageKey);}catch{}
    location.replace(`${base}/confirmacion/${result.id}`);
  }catch(err){
    if(err.detail?.code==='visita_existente'){
      try{sessionStorage.removeItem(storageKey);}catch{}
      existingVisit(form,err.detail.visita_id);return;
    }
    showError(err.message);sending=false;fields.disabled=false;submit.textContent='Revisar solicitud';confirm.disabled=false;edit.disabled=false;confirm.textContent='Confirmar y enviar solicitud';
  }
});
load();
