import {api,base} from './api.js';
import {el,shell,card,state,fail,skeleton,finish} from './utils.js';
shell();
const grid=document.getElementById('results'), form=document.getElementById('filters');
const more=document.getElementById('more'), status=document.getElementById('result-status');
let controller, revision=0, offset=0, query=new URLSearchParams(), loaded=0;
function option(select,value,label){select.append(el('option',{value},label));}
function populate(select,items){
  while(select.options.length>1)select.remove(1);
  for(const [value,label] of items)option(select,value,label);
}
function populateOperations(values=[]){
  const normalized=value=>String(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toLowerCase();
  const buying=new Set(['venta','compra','comprar']);
  const renting=new Set(['alquiler','alquilar']);
  const sale=values.find(value=>buying.has(normalized(value)))||'venta';
  const rent=values.find(value=>renting.has(normalized(value)))||'alquiler';
  populate(form.elements.tipo_operacion,[[sale,'Comprar'],[rent,'Alquilar'],
    ...values.filter(value=>!buying.has(normalized(value))&&!renting.has(normalized(value))).map(value=>[value,value])]);
}
populateOperations();
async function init(){
  try {
    const [context,options]=await Promise.all([api('/lead/contexto'),api('/propiedades/filtros')]);
    if(context.visita_id&&!document.getElementById('existing-visit')){
      grid.before(el('p',{id:'existing-visit',class:'notice'},'Ya tienes una visita solicitada para esta oportunidad. ',el('a',{href:`${base}/confirmacion/${context.visita_id}`,class:'btn text'},'Consultar mi solicitud ↗')));
    }
    if(context.nombre) document.getElementById('welcome').textContent=`Un nuevo comienzo, ${context.nombre.split(' ')[0]}`;
    populateOperations(options.operaciones);
    populate(form.elements.tipo_inmueble,(options.tipos||[]).map(value=>[value,value]));
    populate(form.elements.moneda,(options.monedas||[]).map(value=>[value,value]));
    populate(form.elements.distrito_id,(options.distritos||[]).map(d=>[d.id,d.nombre]));
    document.getElementById('filter-fieldset').disabled=false;
    await load();
  }catch(error){finish(grid);fail(grid,error,init);}
}
async function load(append=false){
  controller?.abort(); controller=new AbortController(); const id=++revision;
  more.disabled=true;
  if(!append){offset=0;loaded=0;skeleton(grid);}
  const params=new URLSearchParams(query); params.set('offset',offset);params.set('limit',12);
  try{
    const rows=await api(`/propiedades?${params}`,{signal:controller.signal});
    if(id!==revision)return;
    if(!append)grid.replaceChildren();
    rows.forEach(p=>grid.append(card(p)));loaded+=rows.length;offset+=rows.length;
    if(!loaded)state(grid,'Un espacio para cada búsqueda','No hay propiedades con estos criterios. Prueba con otro distrito o limpia los filtros.');
    status.textContent=loaded?`${loaded} propiedad${loaded===1?'':'es'} disponible${loaded===1?'':'s'} mostrada${loaded===1?'':'s'}`:'Sin resultados';
    more.hidden=rows.length<12;more.disabled=false;
  }catch(error){
    if(error.name==='AbortError'||id!==revision)return;
    if(append){document.getElementById('filter-error').textContent=error.message;more.disabled=false;}
    else{fail(grid,error,()=>load());more.hidden=true;}
  }finally{if(id===revision)finish(grid);}
}
form.addEventListener('submit',event=>{
  event.preventDefault();const data=new FormData(form);
  const min=data.get('precio_min'),max=data.get('precio_max');
  const error=document.getElementById('filter-error');error.textContent='';
  if(min&&max&&Number(min)>Number(max)){error.textContent='El mínimo no puede superar al máximo.';form.elements.precio_min.focus();return;}
  if((min||max)&&!data.get('moneda')){error.textContent='Elige una moneda para comparar precios.';form.elements.moneda.focus();return;}
  query=new URLSearchParams([...data].filter(([,value])=>value!==''));load();
});
document.getElementById('clear').addEventListener('click',()=>{form.reset();query=new URLSearchParams();document.getElementById('filter-error').textContent='';load();});
document.getElementById('extra-toggle').addEventListener('click',event=>{
  const extra=document.getElementById('extra');extra.hidden=!extra.hidden;
  event.currentTarget.setAttribute('aria-expanded',String(!extra.hidden));
  event.currentTarget.textContent=extra.hidden?'Más filtros +':'Menos filtros −';
});
more.addEventListener('click',()=>load(true));init();
