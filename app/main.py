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
from .schemas import VisitIn, PropertyOut
from .services import require_lead, create_visit, normalize_property

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Raíz Urbana")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
def read_token(value: Annotated[str, Header(alias="X-Lead-Token")]):
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(404, "El enlace no es válido. Solicita uno nuevo por WhatsApp.")


Token = Annotated[UUID, Depends(read_token)]
PROPERTY_FIELDS = "id,titulo,descripcion,tipo_operacion,tipo_inmueble,condicion,proyecto,distrito_id,moneda,precio,cantidad_dormitorios,cantidad_banos,cocheras,area_total,direccion,disponible,distritos(nombre),propiedad_imagenes(id,url,orden)"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update({
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' https:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    })
    return response


@app.exception_handler(APIError)
async def database_error(request, error):
    # Never return raw PostgREST errors: they may include SQL or token values.
    message = error.message or ""
    rules = {
        "RU_TOKEN": (404, "El enlace no es válido."),
        "RU_UNAVAILABLE": (409, "La propiedad ya no está disponible."),
        "RU_DATE": (422, "Elige una fecha y hora futuras en Lima."),
        "RU_CONSENT": (422, "Autoriza el tratamiento de datos para solicitar la visita."),
        "RU_REPLAY": (409, "Esta clave de solicitud ya se utilizó con otros datos."),
    }
    status, detail = next((value for tag, value in rules.items() if tag in message), (503, "No pudimos completar la operación. Revisa la configuración o inténtalo de nuevo."))
    return JSONResponse({"detail": detail}, status_code=status)


@app.exception_handler(Exception)
async def unexpected_error(request, error):
    return JSONResponse({"detail": "El servicio no está disponible temporalmente. Inténtalo de nuevo."}, status_code=503)


@app.get("/api/health")
def health():
    return {"status": "up", "database_checked": False}


@app.get("/api/lead/contexto")
def context(token: Token, db=Depends(get_db)):
    lead = require_lead(db, token)
    return {"nombre": lead["nombre"], "consentimiento": lead["consentimiento"], "privacy_contact": get_settings().privacy_contact}


@app.get("/api/propiedades", response_model=list[PropertyOut])
def properties(token: Token, tipo_operacion: str | None = None, tipo_inmueble: str | None = None,
               distrito_id: int | None = Query(None, gt=0), precio_min: Decimal | None = Query(None, ge=0),
               precio_max: Decimal | None = Query(None, ge=0), dormitorios_min: int | None = Query(None, ge=0),
               moneda: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=60), db=Depends(get_db)):
    require_lead(db, token)
    if precio_min is not None and precio_max is not None and precio_min > precio_max:
        raise HTTPException(422, "El precio mínimo no puede superar al máximo.")
    if (precio_min is not None or precio_max is not None) and not moneda:
        raise HTTPException(422, "Selecciona una moneda para filtrar precios comparables.")
    query = db.table("propiedades").select(PROPERTY_FIELDS).eq("disponible", True)
    for field, value in (("tipo_operacion", tipo_operacion), ("tipo_inmueble", tipo_inmueble), ("distrito_id", distrito_id), ("moneda", moneda)):
        if value is not None:
            query = query.eq(field, value)
    for field, method, value in (("precio", "gte", precio_min), ("precio", "lte", precio_max), ("cantidad_dormitorios", "gte", dormitorios_min)):
        if value is not None:
            query = getattr(query, method)(field, str(value))
    rows = query.order("created_at", desc=True).order("id").range(offset, offset + limit - 1).execute().data
    return [normalize_property(row) for row in rows]


@app.get("/api/propiedades/filtros")
def filter_options(token: Token, db=Depends(get_db)):
    require_lead(db, token)
    # RPC uses DISTINCT server-side, avoiding the default Supabase 1000-row cap.
    return db.rpc("ru_filtros_propiedades", {}).execute().data


@app.get("/api/propiedades/{property_id}", response_model=PropertyOut)
def property_detail(property_id: int, token: Token, db=Depends(get_db)):
    require_lead(db, token)
    rows = db.table("propiedades").select(PROPERTY_FIELDS).eq("id", property_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "No encontramos esta propiedad.")
    return normalize_property(rows[0])


@app.post("/api/visitas", status_code=201)
def submit_visit(body: VisitIn, token: Token, db=Depends(get_db)):
    return create_visit(db, token, body)


@app.get("/api/visitas/mias")
def my_visits(token: Token, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=60), db=Depends(get_db)):
    lead = require_lead(db, token)
    # RPC performs global priority ordering before pagination.
    return db.rpc("ru_mis_visitas", {"p_lead_id": lead["id"], "p_offset": offset, "p_limit": limit,
                                   "p_estado_pendiente": get_settings().initial_visit_state}).execute().data


@app.get("/")
def welcome():
    return FileResponse(ROOT / "static" / "inicio.html")


@app.get("/inmuebles/{token}")
def catalog_page(token: str):
    return FileResponse(ROOT / "static" / "catalogo.html")


@app.get("/inmuebles/{token}/propiedad/{property_id}")
def detail_page(token: str, property_id: int):
    return FileResponse(ROOT / "static" / "detalle.html")


@app.get("/inmuebles/{token}/propiedad/{property_id}/solicitar")
def request_page(token: str, property_id: int):
    return FileResponse(ROOT / "static" / "solicitar-visita.html")


@app.get("/inmuebles/{token}/mis-visitas")
def visits_page(token: str):
    return FileResponse(ROOT / "static" / "mis-visitas.html")


@app.get("/inmuebles/{token}/confirmacion/{visit_id}")
def confirmation_page(token: str, visit_id: int):
    return FileResponse(ROOT / "static" / "confirmacion.html")


@app.get("/api/visitas/{visit_id}")
def get_visit(visit_id: int, token: Token, db=Depends(get_db)):
    lead = require_lead(db, token)
    rows = db.table("visitas").select("id,nombre,fecha_cliente,fecha_acordada,estado_id,motivo,estados_visita(nombre),propiedades(id,titulo,propiedad_imagenes(id,url,orden))").eq("lead_id", lead["id"]).eq("id", visit_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "No encontramos esta solicitud.")
    return rows[0]
