import {base} from './api.js';
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key,value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2),value);
    else if (value !== null && value !== undefined) node.setAttribute(key,String(value));
  }
  for (const child of children.flat()) if (child !== undefined && child !== null) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return node;
}
export const money = (value,currency) => {
  if(value===null||value===undefined||!currency)return 'Precio a consultar';
  const code = ({'S/':'PEN','S/.':'PEN','$':'USD','US$':'USD'})[currency] || currency;
  try { return new Intl.NumberFormat('es-PE',{style:'currency',currency:code,maximumFractionDigits:0}).format(Number(value)); }
  catch { return `${currency} ${Number(value).toLocaleString('es-PE')}`; }
};
export const area = value => value == null ? 'No indicada' : `${Number(value).toLocaleString('es-PE')} m²`;
export const dateText = value => value ? new Intl.DateTimeFormat('es-PE',{dateStyle:'long',timeStyle:'short',timeZone:'America/Lima'}).format(new Date(value)) : 'Por coordinar';
export function photo(url, alt, {lazy=true, thumb=false}={}) {
  let src = '/static/img/placeholder.svg';
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'https:') {
      src = parsed.href;
      // Supabase image transformations may require an enabled project plan.
      // On failure, thumbnail falls back to the original URL, then placeholder.
      if (thumb && parsed.pathname.includes('/storage/v1/object/public/')) {
        parsed.pathname = parsed.pathname.replace('/object/public/','/render/image/public/');
        parsed.searchParams.set('width','180'); parsed.searchParams.set('quality','60'); src=parsed.href;
      }
    }
  } catch {}
  const image = el('img',{src,alt,loading:lazy?'lazy':'eager',decoding:'async'});
  const original=src==='/static/img/placeholder.svg'?src:url;
  let fallback=false;
  image.addEventListener('error',()=>{
    if (thumb && !fallback && src !== original) {fallback=true; image.src=original; return;}
    if (!image.src.endsWith('/static/img/placeholder.svg')) image.src='/static/img/placeholder.svg';
  });
  return image;
}
export function images(property) {return [...(property.propiedad_imagenes || property.imagenes || [])].sort((a,b)=>(a.orden??Infinity)-(b.orden??Infinity)||a.id-b.id);}
export function state(container, title, text, retry) {
  const content=el('div',{class:'state',role:'status'},el('h2',{},title),el('p',{},text));
  if (retry) content.append(el('button',{class:'btn',type:'button',onclick:retry},'Volver a intentar'));
  container.replaceChildren(content);
}
export function fail(container,error,retry) {const invalid=[401,403,404].includes(error.status);state(container,invalid?'Acceso no disponible':'No pudimos cargar la información',error.message,invalid?null:retry);}
export function existingVisit(container,id) {
  container.replaceChildren(el('h2',{},'Ya recibimos tu solicitud'),el('p',{class:'notice'},'Esta oportunidad ya tiene una visita solicitada. Puedes seguir explorando propiedades; las visitas adicionales se coordinan directamente con tu asesor.'),el('a',{class:'btn teal',href:id?`${base}/confirmacion/${id}`:`${base}/mis-visitas`},'Consultar mi solicitud'));
}
export function shell(active='catalogo') {
  const header=document.getElementById('header');
  const back=document.getElementById('back');if(back)back.href=base;
  header.replaceChildren(el('div',{class:'container header-inner'},
    el('a',{class:'brand',href:base,'aria-label':'Raíz Urbana, catálogo'},
      el('img',{class:'brand-logo',src:'/static/img/logotipo-inmobiliaria-sin-fondo.webp',alt:'',width:'60',height:'48'}),
      el('span',{},el('strong',{},'raíz urbana'),el('small',{},'INMOBILIARIA'))),
    el('nav',{class:'nav','aria-label':'Navegación principal'},
      el('a',{href:base,'aria-current':active==='catalogo'?'page':null},'Propiedades'),
      el('a',{href:`${base}/mis-visitas`,'aria-current':active==='visitas'?'page':null},'Mis visitas ↗'))));
  document.getElementById('footer').replaceChildren(el('div',{class:'container'},
    el('span',{},'Raíz Urbana Inmobiliaria · Encuentra tu próximo hogar'),el('span',{},'Lima, Perú · Demo comercial')));
}
export function card(p) {
  const href=`${base}/propiedad/${p.id}`;
  const specs=[
    p.cantidad_dormitorios!=null?`${p.cantidad_dormitorios} dorm.`:null,
    p.cantidad_banos!=null?`${p.cantidad_banos} baños`:null,
    p.area_total!=null?area(p.area_total):null
  ].filter(Boolean);
  return el('article',{class:'card property'},
    el('a',{class:'property-image',href,tabindex:'-1','aria-hidden':'true'},photo(images(p)[0]?.url,p.titulo)),
    el('div',{class:'property-body'},
      el('h3',{},el('a',{href},p.titulo || 'Inmueble disponible')),
      el('div',{class:'features'},specs.map(s=>el('span',{},s))),
      el('a',{class:'property-link',href},'Ver propiedad',el('span',{'aria-hidden':'true'},'↗'))));
}
export function skeleton(container,count=3) {container.replaceChildren(...Array.from({length:count},()=>el('div',{class:'skeleton','aria-hidden':'true'})));container.setAttribute('aria-busy','true');}
export function finish(container) {container.removeAttribute('aria-busy');}
