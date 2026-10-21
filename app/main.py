from pathlib import Path
from decimal import Decimal
from typing import Annotated
from uuid import UUID
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from postgrest.exceptions import APIError
from .db import get_db
from .config import get_settings
from .schemas import PropertyOpportunityIn, PropertyOpportunityOut, VisitIn, PropertyOut, OpportunityContextOut, VisitCreatedOut, VisitOut
from .services import require_opportunity, current_visit, create_visit, normalize_property
from .docs import install_documentation
from .admin import router as admin_router
from .agents import router as agents_router

ROOT = Path(__file__).resolve().parent.parent
# Custom documentation routes allow their CDN assets without relaxing the site CSP.
app = FastAPI(title="Raíz Urbana", docs_url=None, redoc_url=None, openapi_url="/openapi.json")
install_documentation(app)
app.include_router(admin_router)
app.include_router(agents_router)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
def read_token(
    value: Annotated[str | None, Header(alias="X-Opportunity-Token", description="Token UUID de la oportunidad abierta")] = None,
    legacy: Annotated[str | None, Header(alias="X-Lead-Token", deprecated=True, description="Compatibilidad: también debe contener el token de oportunidad")] = None,
):
    if value and legacy and value != legacy:
        raise HTTPException(400, "Los encabezados de acceso no coinciden.")
    raw = value or legacy
    if not raw:
        raise HTTPException(401, "Falta el token de oportunidad.")
    try:
        return UUID(raw)
    except ValueError:
        raise HTTPException(404, "El enlace no es válido. Solicita uno nuevo por WhatsApp.")


Token = Annotated[UUID, Depends(read_token)]
PROPERTY_FIELDS = "id,titulo,descripcion,tipo_operacion,tipo_inmueble,condicion,proyecto,distrito_id,moneda,precio,cantidad_dormitorios,cantidad_banos,cocheras,area_total,direccion,disponible,distritos(nombre),propiedad_imagenes(id,url,orden,categoria)"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update({
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    })
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' https:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if request.url.path == '/agente/propiedades':
        response.headers['Content-Security-Policy'] = response.headers['Content-Security-Policy'].replace("img-src 'self' https:","img-src 'self' https: blob:")
    return response


@app.exception_handler(APIError)
async def database_error(request, error):
    # Never return raw PostgREST errors: they may include SQL or token values.
    message = error.message or ""
    if request.url.path == "/api/oportunidades/resolver" and error.code == "PGRST202":
        return JSONResponse({"detail": "Falta configurar las oportunidades por inmueble. Aplica la migracion 06 en Supabase."}, status_code=503)
    rules = {
        "RU_ADMIN_PROPERTY": (404, "La propiedad no existe."),
        "RU_ADMIN_IMAGE": (404, "La imagen ya no existe."),
        "RU_ADMIN_ORDER": (409, "Las imágenes cambiaron. Recarga la lista antes de ordenarlas."),
        "RU_TOKEN": (404, "El enlace no es válido."),
        "RU_CLOSED": (403, "Esta oportunidad ya está cerrada. Solicita un nuevo enlace por WhatsApp."),
        "RU_UNAVAILABLE": (409, "La propiedad ya no está disponible."),
        "RU_DATE": (422, "Elige una fecha y hora futuras en Lima."),
        "RU_CONSENT": (422, "Autoriza el tratamiento de datos para solicitar la visita."),
        "RU_REPLAY": (409, "Esta clave de solicitud ya se utilizó con otros datos."),
    }
    if request.url.path.startswith('/api/agente/') and error.code in ('23503','23514','23505'):
        return JSONResponse({'detail':'No se pudo guardar: revisa las referencias y los valores; otro agente pudo modificarlos.'},status_code=409)
    for tag, text in (("RU_PROPERTY_MISMATCH", "La oportunidad ya esta asociada a otro inmueble."),
                      ("RU_PROPERTY_ALREADY_OPEN", "Ya existe una oportunidad abierta para este inmueble. Consulta su solicitud.")):
        if tag in message:
            return JSONResponse({"detail": {"code": tag, "mensaje": text}}, status_code=409)
    if "RU_VISIT_EXISTS" in message:
        raw_id = str(error.details or "")
        visit_id = int(raw_id) if raw_id.isdigit() else None
        return JSONResponse({"detail": {"code": "visita_existente", "mensaje": "Ya solicitaste una visita para esta oportunidad.", "visita_id": visit_id}}, status_code=409)
    status, detail = next((value for tag, value in rules.items() if tag in message), (503, "No pudimos completar la operación. Revisa la configuración o inténtalo de nuevo."))
    return JSONResponse({"detail": detail}, status_code=status)


@app.exception_handler(Exception)
async def unexpected_error(request, error):
    return JSONResponse({"detail": "El servicio no está disponible temporalmente. Inténtalo de nuevo."}, status_code=503)


@app.get("/api/health")
def health():
    return {"status": "up", "database_checked": False}


@app.get("/api/lead/contexto", response_model=OpportunityContextOut)
def context(token: Token, db=Depends(get_db)):
    opportunity = require_opportunity(db, token)
    visit = current_visit(db, opportunity["id"])
    return {"nombre": opportunity["leads"]["nombre"], "telefono": opportunity["leads"].get("telefono"), "estado_oportunidad": opportunity["estado_oportunidad"]["nombre"],
            "propiedad_id": opportunity.get("propiedad_id"), "visita_id": visit["id"] if visit else None, "puede_solicitar": visit is None,
            "privacy_contact": get_settings().privacy_contact}


@app.post("/api/oportunidades/resolver", response_model=PropertyOpportunityOut, tags=["Oportunidades"], summary="Resolver una oportunidad del mismo lead para otro inmueble")
def resolve_property_opportunity(body: PropertyOpportunityIn, token: Token, db=Depends(get_db)):
    require_opportunity(db, token)
    return db.rpc("ru_resolver_oportunidad_propiedad", {"p_token": str(token), "p_propiedad_id": body.propiedad_id}).execute().data


@app.get("/api/propiedades", response_model=list[PropertyOut])
def properties(token: Token, tipo_operacion: str | None = None, tipo_inmueble: str | None = None,
               distrito_id: int | None = Query(None, gt=0), precio_min: Decimal | None = Query(None, ge=0),
               precio_max: Decimal | None = Query(None, ge=0), dormitorios_min: int | None = Query(None, ge=0),
               moneda: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=60), db=Depends(get_db)):
    require_opportunity(db, token)
    if precio_min is not None and precio_max is not None and precio_min > precio_max:
        raise HTTPException(422, "El precio mínimo no puede superar al máximo.")
    if (precio_min is not None or precio_max is not None) and not moneda:
        raise HTTPException(422, "Selecciona una moneda para filtrar precios comparables.")
    query = db.table("propiedades").select(PROPERTY_FIELDS).eq("disponible", True)
    for field, value in (("tipo_operacion", tipo_operacion), ("tipo_inmueble", tipo_inmueble), ("distrito_id", distrito_id), ("moneda", moneda)):
        if value is not None:
            query = query.ilike(field, value) if field == "tipo_operacion" else query.eq(field, value)
    for field, method, value in (("precio", "gte", precio_min), ("precio", "lte", precio_max), ("cantidad_dormitorios", "gte", dormitorios_min)):
        if value is not None:
            query = getattr(query, method)(field, str(value))
    rows = query.order("created_at", desc=True).order("id").range(offset, offset + limit - 1).execute().data
    return [normalize_property(row) for row in rows]


@app.get("/api/propiedades/filtros")
def filter_options(token: Token, db=Depends(get_db)):
    require_opportunity(db, token)
    # Metadata is not restricted to currently available properties. Districts
    # come from their own registry, not from the current search results.
    def read_all(table, fields):
        rows = []
        offset = 0
        while True:
            batch = db.table(table).select(fields).order("id").range(offset, offset + 499).execute().data
            rows.extend(batch)
            if len(batch) < 500:
                return rows
            offset += len(batch)

    registered = read_all("propiedades", "id,tipo_operacion,tipo_inmueble,moneda")
    districts = read_all("distritos", "id,nombre")
    def values(field):
        return sorted({r[field] for r in registered if isinstance(r.get(field), str) and r[field].strip()}, key=str.casefold)
    return {"operaciones": values("tipo_operacion"), "tipos": values("tipo_inmueble"),
            "monedas": values("moneda"), "distritos": sorted(districts, key=lambda d: d["nombre"].casefold())}


@app.get("/api/propiedades/{property_id}", response_model=PropertyOut)
def property_detail(property_id: int, token: Token, db=Depends(get_db)):
    require_opportunity(db, token)
    rows = db.table("propiedades").select(PROPERTY_FIELDS).eq("id", property_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "No encontramos esta propiedad.")
    return normalize_property(rows[0])


@app.post("/api/visitas", response_model=VisitCreatedOut, status_code=201)
def submit_visit(body: VisitIn, token: Token, db=Depends(get_db)):
    return create_visit(db, token, body)


@app.get("/api/visitas/mias", response_model=list[VisitOut])
def my_visits(token: Token, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=60), db=Depends(get_db)):
    require_opportunity(db, token)
    # RPC performs global priority ordering before pagination.
    return db.rpc("ru_mis_visitas_oportunidades", {"p_token": str(token), "p_offset": offset, "p_limit": limit,
                                   "p_estado_pendiente": get_settings().initial_visit_state}).execute().data


@app.get("/api/visitas/actual", response_model=VisitOut)
def opportunity_visit(token: Token, db=Depends(get_db)):
    opportunity = require_opportunity(db, token)
    visit = current_visit(db, opportunity["id"])
    if not visit:
        raise HTTPException(404, "Todavía no solicitaste una visita para esta oportunidad.")
    return get_visit(visit["id"], token, db)


def opportunity_page(token, filename, db):
    try:
        parsed = UUID(token)
    except ValueError:
        return FileResponse(ROOT / "static" / "acceso-invalido.html", status_code=404)
    try:
        require_opportunity(db, parsed)
    except HTTPException as error:
        if error.status_code in (403, 404):
            return FileResponse(ROOT / "static" / "acceso-invalido.html", status_code=error.status_code)
        raise
    return FileResponse(ROOT / "static" / filename)


@app.get("/", include_in_schema=False)
def welcome():
    return FileResponse(ROOT / "static" / "inicio.html")


@app.get("/inmuebles/{token}", include_in_schema=False)
def catalog_page(token: str, db=Depends(get_db)):
    return opportunity_page(token, "catalogo.html", db)


@app.get("/inmuebles/{token}/propiedad/{property_id}", include_in_schema=False)
def detail_page(token: str, property_id: int, db=Depends(get_db)):
    return opportunity_page(token, "detalle.html", db)


@app.get("/inmuebles/{token}/propiedad/{property_id}/solicitar", include_in_schema=False)
def request_page(token: str, property_id: int, db=Depends(get_db)):
    return opportunity_page(token, "solicitar-visita.html", db)


@app.get("/inmuebles/{token}/mis-visitas", include_in_schema=False)
def visits_page(token: str, db=Depends(get_db)):
    return opportunity_page(token, "mis-visitas.html", db)


@app.get("/inmuebles/{token}/confirmacion/{visit_id}", include_in_schema=False)
def confirmation_page(token: str, visit_id: int, db=Depends(get_db)):
    return opportunity_page(token, "confirmacion.html", db)


@app.get("/api/visitas/{visit_id}", response_model=VisitOut)
def get_visit(visit_id: int, token: Token, db=Depends(get_db)):
    opportunity = require_opportunity(db, token)
    rows = (db.table("visitas")
            .select("id,oportunidad_id,fecha_cliente,fecha_agente,fecha_acordada,estado_id,estados_visita(nombre),propiedades!visitas_propiedad_id_fkey(id,titulo,propiedad_imagenes(id,url,orden)),oportunidades!inner(lead_id)")
            .eq("oportunidades.lead_id", opportunity["lead_id"]).eq("id", visit_id).limit(1).execute().data)
    if not rows:
        raise HTTPException(404, "No encontramos esta solicitud.")
    row = rows[0]
    row.pop("oportunidades", None)
    row["es_oportunidad_actual"] = row["oportunidad_id"] == opportunity["id"]
    return row
