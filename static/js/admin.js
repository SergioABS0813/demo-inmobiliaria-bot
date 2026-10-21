import {el,photo,money} from './utils.js';

const $=id=>document.getElementById(id);
const form=$('property-form'),fields=$('property-fields'),mediaFields=$('media-fields');
const labels={vista_1:'Áreas sociales',vista_2:'Áreas privadas',plano:'Plano',legacy:'Sin clasificar'};
const state={id:null,offset:0,total:0,images:[],saving:false,mediaBusy:false,orderDirty:false,propertyDirty:false,options:null,listRevision:0,editorRevision:0,listController:null,previews:[]};
const numbers=new Set(['distrito_id','cantidad_dormitorios','cantidad_banos','cocheras','agente_id']);
const decimals=new Set(['precio','area_total']);

async function api(path,{method='GET',body,signal,timeout=20000}={}){
  const controller=new AbortController(),abort=()=>controller.abort();
  signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();
  const timer=setTimeout(abort,timeout);
  try{
    const headers=method==='GET'?{}:{'X-RU-Admin':'1'};
    const multipart=body instanceof FormData;
    if(body&&!multipart)headers['Content-Type']='application/json';
    const response=await fetch('/api/agente'+path,{method,headers,body:body?(multipart?body:JSON.stringify(body)):undefined,credentials:'same-origin',cache:'no-store',signal:controller.signal});
    const data=await response.json().catch(()=>({}));
    if(!response.ok){
      let message=typeof data.detail==='string'?data.detail:'No se pudo completar la operación.';
      if(Array.isArray(data.detail))message=data.detail.map(item=>`${item.loc?.slice(-1)[0]||'Campo'}: ${item.msg}`).join(' · ');
      throw new Error(message);
    }
    return data;
  }catch(error){
    if(signal?.aborted)throw new DOMException('Cancelado','AbortError');
    if(error.name==='AbortError'||error instanceof TypeError)throw new Error('No pudimos confirmar la respuesta. Revisa la conexión y recarga los datos antes de repetir la operación.');
    throw error;
  }finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}

function notice(text,error=false,focus=false){
  const box=$('notice');box.textContent=text;box.hidden=!text;box.className=error?'error':'notice';box.setAttribute('role',error?'alert':'status');
  if(focus){box.focus();box.scrollIntoView({block:'nearest'});}
}
function fillSelect(select,items){
  while(select.options.length>1)select.remove(1);
  items.forEach(([value,label])=>select.append(el('option',{value},label)));
}
function setValue(control,value){
  if(control.type==='checkbox'){control.checked=Boolean(value);return;}
  if(control.tagName==='SELECT'&&value!=null&&![...control.options].some(o=>o.value===String(value)))control.append(el('option',{value},String(value)));
  control.value=value??'';
}
async function initialize(){
  try{
    state.options=await api('/opciones');
    fillSelect($('district-filter'),state.options.distritos.map(d=>[d.id,d.nombre]));
    fillSelect(form.elements.distrito_id,state.options.distritos.map(d=>[d.id,d.nombre+(d.activo?'':' · Inactivo')]));
    fillSelect(form.elements.agente_id,state.options.agentes.map(a=>[a.id,a.nombre||`Agente #${a.id}`]));
    $('new-property').disabled=false;
    await loadList();refreshCleanup();
    const edit=new URLSearchParams(location.search).get('editar');
    if(edit&&/^\d+$/.test(edit))openEditor(Number(edit));
  }catch(error){notice(error.message,true);$('list-status').textContent='No se pudo cargar el panel. Recarga para reintentar.';}
}

async function loadList(){
  state.listController?.abort();state.listController=new AbortController();const revision=++state.listRevision;
  $('properties-body').setAttribute('aria-busy','true');$('previous').disabled=true;$('next').disabled=true;
  $('list-status').textContent='Actualizando listado…';
  $('properties-body').replaceChildren(el('tr',{},el('td',{colspan:9},el('span',{class:'admin-inline-loader'},el('span',{class:'admin-spinner','aria-hidden':'true'}),'Cargando propiedades…'))));
  const params=new URLSearchParams({offset:state.offset,limit:25});
  if($('search').value.trim())params.set('q',$('search').value.trim());
  if($('district-filter').value)params.set('distrito_id',$('district-filter').value);
  if($('availability-filter').value)params.set('disponible',$('availability-filter').value);
  try{
    const data=await api('/propiedades?'+params,{signal:state.listController.signal});
    if(revision!==state.listRevision)return;
    state.total=data.total??data.propiedades.length;
    if(state.offset>=state.total&&state.offset>0){state.offset=Math.max(0,state.offset-25);return loadList();}
    $('properties-body').replaceChildren(...data.propiedades.map(row=>{
      const edit=el('button',{class:'btn secondary',type:'button',onclick:()=>openEditor(row.id)},'Editar');
      const toggle=el('button',{class:'btn secondary'+(row.disponible?' danger':''),type:'button',onclick:()=>toggleAvailability(row,toggle)},row.disponible?'Desactivar':'Activar');
      return el('tr',{},el('td',{},row.id),el('td',{},row.titulo||'Sin título'),el('td',{},row.distritos?.nombre||'—'),
        el('td',{},row.tipo_inmueble||'—'),el('td',{},row.tipo_operacion||'—'),el('td',{},money(row.precio,row.moneda)),
        el('td',{},row.agentes?.nombre||'Sin asignar'),el('td',{},el('span',{class:'pill'+(row.disponible?'':' inactive')},row.disponible?'Disponible':'Desactivada')),
        el('td',{},el('div',{class:'table-actions'},edit,toggle)));
    }));
    if(!data.propiedades.length)$('properties-body').append(el('tr',{},el('td',{colspan:9},'No hay propiedades con estos criterios.')));
    $('list-status').textContent=`${state.total} propiedad${state.total===1?'':'es'} · Las desactivadas conservan sus datos y visitas.`;
    $('page-position').textContent=state.total?`${state.offset+1}–${state.offset+data.propiedades.length} de ${state.total}`:'Sin resultados';
    $('previous').disabled=state.offset===0;$('next').disabled=state.offset+25>=state.total;
    return true;
  }catch(error){if(error.name!=='AbortError'){notice(error.message,true);$('list-status').textContent='La lista no está actualizada.';$('properties-body').replaceChildren(el('tr',{},el('td',{colspan:9},'No se pudo cargar el listado. Pulsa Buscar para reintentar.')));}return false;}
  finally{if(revision===state.listRevision)$('properties-body').removeAttribute('aria-busy');}
}
async function toggleAvailability(row,button){
  if(row.disponible&&!confirm(`¿Desactivar “${row.titulo||'esta propiedad'}”? Se conservarán sus datos y visitas.`))return;
  button.disabled=true;
  try{await api(`/propiedades/${row.id}/disponibilidad`,{method:'PATCH',body:{disponible:!row.disponible}});notice(row.disponible?'Propiedad desactivada.':'Propiedad disponible en el catálogo.');await loadList();}
  catch(error){notice(error.message,true);button.disabled=false;}
}
function canLeave(){
  if(state.saving||state.mediaBusy){notice('Espera a que termine la operación en curso.',true);return false;}
  if((state.orderDirty||state.propertyDirty)&&!confirm('Hay cambios sin guardar. ¿Descartarlos?'))return false;
  return true;
}
async function openEditor(id=null){
  if(!canLeave())return;
  const revision=++state.editorRevision;state.id=id;state.images=[];state.orderDirty=false;state.propertyDirty=false;
  $('list-view').hidden=true;$('editor-view').hidden=false;notice('');clearPreviews();form.reset();
  fields.disabled=true;mediaFields.disabled=true;$('images-list').replaceChildren();$('save-order').disabled=true;
  $('editor-title').textContent=id?`Editar propiedad #${id}`:'Nueva propiedad';
  $('editor-subtitle').textContent=id?'Actualiza los datos o administra sus fotografías.':'Guarda la propiedad para añadir sus fotografías y planos.';
  $('images-status').textContent=id?'Cargando imágenes…':'Primero guarda la propiedad.';
  history.replaceState(null,'',id?`?editar=${id}`:location.pathname);
  try{
    if(id){
      const [property,images]=await Promise.all([api(`/propiedades/${id}`),api(`/propiedades/${id}/imagenes`)]);
      if(revision!==state.editorRevision)return;
      for(const control of form.elements)if(control.name)setValue(control,property[control.name]);
      state.images=images;renderImages();mediaFields.disabled=false;
    }
    fields.disabled=false;
    $('media-help').textContent=id?`Carpeta: propiedad_${id}/ · La primera imagen será la portada del catálogo.`:'Primero guarda la propiedad. Las carpetas se crean automáticamente al subir archivos.';
    $('editor-title').setAttribute('tabindex','-1');$('editor-title').focus();
  }catch(error){if(revision===state.editorRevision)notice(error.message,true,true);}
}
form.addEventListener('submit',async event=>{
  event.preventDefault();if(state.saving||state.mediaBusy)return;
  if(state.orderDirty){notice('Guarda primero el orden de las imágenes antes de guardar y volver al listado.',true,true);return;}
  const body={};
  for(const control of form.elements){
    if(!control.name)continue;
    const value=control.value.trim();
    body[control.name]=control.type==='checkbox'?control.checked:numbers.has(control.name)?(value===''?null:Number(value)):decimals.has(control.name)?(value||null):(value||null);
  }
  state.saving=true;fields.disabled=true;mediaFields.disabled=true;
  form.setAttribute('aria-busy','true');$('save-property').classList.add('is-loading');$('save-property').textContent='Guardando…';
  try{
    const result=await api(state.id?`/propiedades/${state.id}`:'/propiedades',{method:state.id?'PATCH':'POST',body});
    state.id=result.id;state.propertyDirty=false;
    const refreshed=await returnToList(true);
    notice(refreshed?'Propiedad guardada. Puedes pulsar Editar para gestionar sus fotografías.':'La propiedad se guardó, pero no pudimos actualizar el listado. Pulsa Buscar para recargar.',!refreshed,true);
  }catch(error){notice(error.message,true,true);}
  finally{state.saving=false;fields.disabled=false;mediaFields.disabled=!state.id;form.removeAttribute('aria-busy');$('save-property').classList.remove('is-loading');$('save-property').textContent='Guardar propiedad';}
});

form.addEventListener('input',()=>{state.propertyDirty=true;});
function mediaNotice(text,error=false){
  const box=$('media-notice');box.textContent=text;box.hidden=!text;
  box.className=error?'error':'notice';box.setAttribute('role',error?'alert':'status');
}
function clearPreviews(){state.previews.forEach(url=>URL.revokeObjectURL(url));state.previews=[];$('upload-previews').replaceChildren();$('image-files').value='';}
$('image-files').addEventListener('change',()=>{
  state.previews.forEach(url=>URL.revokeObjectURL(url));state.previews=[];$('upload-previews').replaceChildren();
  mediaNotice('');
  const files=[...$('image-files').files];
  if(files.length>6||files.some(f=>f.size>8*1024*1024)||files.reduce((n,f)=>n+f.size,0)>24*1024*1024){clearPreviews();mediaNotice('Selecciona hasta 6 imágenes, de máximo 8 MB cada una y 24 MB en total.',true);return;}
  for(const file of files){
    const url=URL.createObjectURL(file);state.previews.push(url);
    $('upload-previews').append(el('figure',{},el('img',{src:url,alt:`Vista previa de ${file.name}`}),el('figcaption',{},file.name)));
  }
});
function mediaBusy(value){
  state.mediaBusy=value;mediaFields.disabled=value||!state.id;
  $('save-order').disabled=value||!state.orderDirty;
  $('images-list').querySelectorAll('button').forEach(button=>button.disabled=value||button.dataset.boundary==='true');
}
async function refreshImages(){state.images=await api(`/propiedades/${state.id}/imagenes`);state.orderDirty=false;renderImages();}
function renderImages(focusId=null,focusAction=null){
  $('images-list').replaceChildren(...state.images.map((image,index)=>{
    const up=el('button',{class:'icon-btn',type:'button','aria-label':'Mover fotografía hacia el inicio','data-action':'up',onclick:()=>moveImage(index,-1)},'↑');
    const down=el('button',{class:'icon-btn',type:'button','aria-label':'Mover fotografía hacia el final','data-action':'down',onclick:()=>moveImage(index,1)},'↓');
    up.dataset.boundary=String(index===0);down.dataset.boundary=String(index===state.images.length-1);
    up.disabled=index===0;down.disabled=index===state.images.length-1;
    const remove=el('button',{class:'btn secondary danger',type:'button',onclick:()=>deleteImage(image)},'Eliminar');
    return el('article',{class:'admin-image','data-image':image.id},photo(image.url,`Fotografía ${index+1}, ${labels[image.categoria]||labels.legacy}`,{thumb:true}),
      el('div',{class:'admin-image-body'},el('p',{},`${index+1}. ${labels[image.categoria]||labels.legacy}${index===0?' · Portada':''}`),el('div',{class:'image-actions'},up,down,remove)));
  }));
  $('images-status').textContent=`${state.images.length} imagen${state.images.length===1?'':'es'} · ${state.orderDirty?'Orden modificado, guarda los cambios.':'Orden del catálogo.'}`;
  $('save-order').disabled=!state.orderDirty||state.mediaBusy;
  if(focusId){const card=$('images-list').querySelector(`[data-image="${focusId}"]`);const target=card?.querySelector(`[data-action="${focusAction}"]`);(target&&!target.disabled?target:card?.querySelector('button:not(:disabled)'))?.focus();}
}
function moveImage(index,delta){
  if(state.mediaBusy||state.saving)return;
  const target=index+delta;if(target<0||target>=state.images.length)return;
  const id=state.images[index].id;
  [state.images[index],state.images[target]]=[state.images[target],state.images[index]];state.orderDirty=true;renderImages(id,delta<0?'up':'down');
}
$('save-order').addEventListener('click',async()=>{
  if(state.mediaBusy||state.saving)return;mediaBusy(true);
  try{state.images=await api(`/propiedades/${state.id}/imagenes/orden`,{method:'PUT',body:{ids:state.images.map(i=>i.id)}});state.orderDirty=false;renderImages();notice('Orden guardado. La primera fotografía será la portada.');}
  catch(error){notice(error.message,true);try{await refreshImages();}catch{}}
  finally{mediaBusy(false);}
});
$('upload-form').addEventListener('submit',async event=>{
  event.preventDefault();if(state.mediaBusy||state.saving||!state.id)return;
  if(state.orderDirty){mediaNotice('Guarda primero el orden de las imágenes.',true);return;}
  const files=[...$('image-files').files];if(!files.length){mediaNotice('Selecciona al menos una imagen.',true);return;}
  const data=new FormData();data.append('categoria',$('image-category').value);files.forEach(file=>data.append('files',file));
  mediaNotice('');$('upload-form').setAttribute('aria-busy','true');$('upload-images').classList.add('is-loading');
  mediaBusy(true);$('upload-images').textContent='Subiendo…';
  try{
    const result=await api(`/propiedades/${state.id}/imagenes`,{method:'POST',body:data,timeout:120000});
    const images=new Map(state.images.map(image=>[image.id,image]));
    result.imagenes.forEach(image=>images.set(image.id,image));
    state.images=[...images.values()].sort((a,b)=>(a.orden??0)-(b.orden??0));
    renderImages();clearPreviews();
    const errors=result.errores.map(error=>`${error.archivo}: ${error.mensaje}${error.ruta_pendiente?' Ruta para revisión: '+error.ruta_pendiente:''}`).join(' ');
    mediaNotice(`${result.imagenes.length} imagen(es) guardada(s). ${errors}`,Boolean(errors));
    refreshCleanup();
  }catch(error){mediaNotice(error.message,true);}
  finally{$('upload-form').removeAttribute('aria-busy');$('upload-images').classList.remove('is-loading');mediaBusy(false);$('upload-images').textContent='Subir imágenes';}
});
async function deleteImage(image){
  if(state.mediaBusy||state.saving)return;
  if(state.orderDirty){notice('Guarda primero el orden de las imágenes.',true);return;}
  if(!confirm('¿Eliminar esta imagen del inmueble? El archivo administrado se retirará de Storage. Las URLs externas solo se desvinculan.'))return;
  mediaBusy(true);
  try{
    const result=await api(`/propiedades/${state.id}/imagenes/${image.id}`,{method:'DELETE'});await refreshImages();
    notice(result.pendientes_revisados?'Imagen retirada. Hay archivos pendientes de limpieza; puedes reintentar desde el listado.':result.archivo_externo_conservado?'Imagen desvinculada. El archivo externo se conservó.':'Imagen eliminada.');refreshCleanup();
  }catch(error){notice(error.message,true);try{await refreshImages();}catch{}}
  finally{mediaBusy(false);}
}
async function refreshCleanup(){try{const data=await api('/archivos-pendientes');$('cleanup-box').hidden=!data.total;}catch{}}
$('retry-cleanup').addEventListener('click',async()=>{
  $('retry-cleanup').disabled=true;
  try{const result=await api('/archivos-pendientes/reintentar',{method:'POST'});notice(`${result.eliminados} archivo(s) retirado(s) de Storage.`);await refreshCleanup();}
  catch(error){notice(error.message,true);}finally{$('retry-cleanup').disabled=false;}
});
$('search-form').addEventListener('submit',event=>{event.preventDefault();state.offset=0;loadList();});
$('clear-search').addEventListener('click',()=>{$('search-form').reset();state.offset=0;loadList();});
$('previous').addEventListener('click',()=>{state.offset=Math.max(0,state.offset-25);loadList();});
$('next').addEventListener('click',()=>{state.offset+=25;loadList();});
$('new-property').addEventListener('click',()=>openEditor());
async function returnToList(resetFilters=false){
  ++state.editorRevision;state.orderDirty=false;state.propertyDirty=false;clearPreviews();
  $('editor-view').hidden=true;$('list-view').hidden=false;history.replaceState(null,'',location.pathname);
  if(resetFilters){$('search-form').reset();state.offset=0;}
  const refreshed=await loadList();refreshCleanup();$('new-property').focus();return refreshed;
}
$('back-list').addEventListener('click',()=>{if(canLeave())returnToList();});
window.addEventListener('beforeunload',event=>{if(state.saving||state.mediaBusy||state.orderDirty||state.propertyDirty){event.preventDefault();event.returnValue='';}});
initialize();
