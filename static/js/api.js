const segments = location.pathname.split('/').filter(Boolean);
export let token = segments[0] === 'inmuebles' ? segments[1] : null;
export let base = token ? `/inmuebles/${encodeURIComponent(token)}` : '/';
export const propertyId = segments[2] === 'propiedad' ? Number(segments[3]) : null;

export class ApiError extends Error {
  constructor(message, status, detail=null) { super(message); this.status = status; this.detail=detail; }
}
export async function api(path, {signal, body, method = 'GET'} = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener('abort', abort, {once:true});
  const timer = setTimeout(abort, 18000);
  try {
    const response = await fetch(`/api${path}`, {
      method, headers: {'X-Opportunity-Token':token || '', ...(body ? {'Content-Type':'application/json'} : {})},
      body:body ? JSON.stringify(body) : undefined, signal:controller.signal, cache:'no-store', credentials:'omit',
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const text = typeof data.detail === 'string' ? data.detail : data.detail?.mensaje || 'Revisa los campos e inténtalo de nuevo.';
      throw new ApiError(text, response.status, data.detail);
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (signal?.aborted) throw new DOMException('Cancelado','AbortError');
    throw new ApiError('No pudimos conectar. Revisa tu conexión e inténtalo de nuevo.', 0);
  } finally {
    clearTimeout(timer); signal?.removeEventListener('abort', abort);
  }
}

export function setOpportunityToken(value){
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value))throw new ApiError('El servidor devolvio un enlace no valido.',503);
  token=value;base=`/inmuebles/${encodeURIComponent(token)}`;
}
