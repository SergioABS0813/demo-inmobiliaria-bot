import {api,base,propertyId} from './api.js';
import {el,shell,photo,images,money,area,fail,finish} from './utils.js';
shell();
const main=document.getElementById('detail');
async function load(){
  try{
    const [p,context]=await Promise.all([api(`/propiedades/${propertyId}`),api('/lead/contexto')]);document.title=`${p.titulo} · Raíz Urbana`;
    const href=context.visita_id?`${base}/confirmacion/${context.visita_id}`:`${base}/propiedad/${p.id}/solicitar`;
    const actionLabel=context.visita_id?'Consultar mi solicitud':'Solicitar una visita ↗';
    const price=money(p.precio,p.moneda);
    const heading=el('div',{class:'detail-heading'},el('div',{},el('span',{class:'pill'},p.tipo_operacion),
      el('h1',{},p.titulo),el('p',{},[p.direccion,p.distrito].filter(Boolean).join(' · '))),el('div',{class:'detail-price'},price));
    const gallery=buildGallery(p);
    const specs=[[area(p.area_total),'Área total'],[p.cantidad_dormitorios,'Dormitorios'],[p.cantidad_banos,'Baños'],[p.cocheras,'Cocheras']]
      .filter(([value])=>value!==null&&value!==undefined);
    const description=el('div',{},el('h2',{},'Un lugar para tu próxima etapa'),
      el('p',{class:'description'},p.descripcion || 'Consulta con el asesor para conocer más sobre esta propiedad.'),
      el('div',{class:'specs'},specs.map(([value,label])=>el('div',{class:'spec'},el('strong',{},value),el('span',{},label)))),
      el('h2',{},'Detalles de la propiedad'));
    const definitions=el('dl',{class:'details'});
    for(const [label,value] of [['Tipo de inmueble',p.tipo_inmueble],['Operación',p.tipo_operacion],['Condición',p.condicion],['Proyecto',p.proyecto],['Distrito',p.distrito],['Disponibilidad',p.disponible?'Disponible':'No disponible']]){
      if(value)definitions.append(el('div',{},el('dt',{},label),el('dd',{},value)));
    }
    description.append(definitions);
    const action=p.disponible||context.visita_id?el('a',{class:'btn teal',href},actionLabel):el('p',{class:'error'},'Esta propiedad ya no está disponible para nuevas visitas.');
    const aside=el('aside',{class:'card visit-cta'},el('span',{class:'eyebrow'},'Da el siguiente paso'),el('h2',{},'Conoce tu próximo hogar'),
      el('p',{},'Recorre el espacio, resuelve tus dudas y descubre si es el lugar para ti.'),action,
      el('small',{},context.visita_id?'Esta oportunidad ya tiene una visita solicitada. Coordina visitas adicionales con tu asesor.':'La fecha que elijas es una preferencia. Nuestro asesor coordinará la visita contigo.'),
      el('div',{class:'trust-line'},'Atención cercana, de principio a fin.'));
    main.replaceChildren(heading,gallery,el('div',{class:'detail-layout'},description,aside));
    if(p.disponible||context.visita_id)main.append(el('div',{class:'mobile-cta'},el('div',{},el('small',{},p.tipo_operacion),el('strong',{},price)),el('a',{class:'btn teal',href},actionLabel)));
  }catch(error){fail(main,error,load);}finally{finish(main);}
}
function buildGallery(p){
  const list=images(p);if(!list.length)list.push({url:null});let index=0;
  const imageName=i=>list[i].categoria==='plano'?'Plano de distribución':list[i].categoria==='vista_1'?'Áreas sociales':list[i].categoria==='vista_2'?'Áreas privadas':`Fotografía ${i+1}`;
  const stage=el('div',{class:'gallery-stage','aria-label':'Galería de la propiedad'});
  const current=photo(list[0].url,`${p.titulo}, ${imageName(0)}`,{lazy:false});current.className='gallery-main';
  const count=el('span',{class:'gallery-count',role:'status'},`${list[0].categoria==='plano'?'Plano · ':''}1 / ${list.length}`);
  const thumbs=el('div',{class:'thumbnails','aria-label':'Seleccionar fotografía'});
  const dialog=document.getElementById('photo-dialog'),full=document.getElementById('full-photo');
  let lastFocus;
  function update(next){
    index=(next+list.length)%list.length;
    const replacement=photo(list[index].url,`${p.titulo}, ${imageName(index)}`,{lazy:false});replacement.className='gallery-main';
    stage.querySelector('.gallery-main').replaceWith(replacement);
    count.textContent=`${list[index].categoria==='plano'?'Plano · ':''}${index+1} / ${list.length}`;
    thumbs.querySelectorAll('button').forEach((button,i)=>button.setAttribute('aria-pressed',String(i===index)));
    if(dialog.open)updateFull();
  }
  function updateFull(){full.replaceChildren(photo(list[index].url,`${p.titulo}, ${imageName(index)} ampliada`,{lazy:false}));full.firstChild.className='dialog-photo';document.getElementById('photo-position').textContent=`${index+1} de ${list.length}`;}
  const prev=()=>update(index-1),next=()=>update(index+1);
  stage.append(current,el('div',{class:'gallery-nav'},el('button',{class:'icon-btn',type:'button','aria-label':'Fotografía anterior',onclick:prev},'‹'),count,el('button',{class:'icon-btn',type:'button','aria-label':'Fotografía siguiente',onclick:next},'›')),
    el('button',{class:'btn gallery-open',type:'button',onclick:event=>{lastFocus=event.currentTarget;dialog.showModal();updateFull();}},'⤢ Ampliar'));
  list.forEach((image,i)=>thumbs.append(el('button',{class:'thumb',type:'button','aria-label':`Ver ${imageName(i)}, ${i+1}`,'aria-pressed':String(i===0),onclick:()=>update(i)},photo(image.url,`${p.titulo}, ${imageName(i)}`,{thumb:true}))));
  document.getElementById('photo-prev').onclick=prev;document.getElementById('photo-next').onclick=next;
  document.getElementById('photo-close').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{full.replaceChildren();lastFocus?.focus();});
  dialog.addEventListener('keydown',event=>{if(event.key==='ArrowLeft'){event.preventDefault();prev();}if(event.key==='ArrowRight'){event.preventDefault();next();}});
  let start;stage.addEventListener('touchstart',event=>{start=event.touches[0].clientX;},{passive:true});
  stage.addEventListener('touchend',event=>{const delta=event.changedTouches[0].clientX-start;if(Math.abs(delta)>55)(delta>0?prev:next)();},{passive:true});
  return el('section',{class:'gallery'},stage,thumbs);
}
load();
