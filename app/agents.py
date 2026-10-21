from pathlib import Path
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from .db import get_db
from .config import get_settings

router = APIRouter(tags=["Agentes"])
ROOT = Path(__file__).resolve().parents[1]

def agent_token(value: Annotated[str | None, Header(alias="X-Agent-Token", description="Token UUID del agente")] = None):
    if not value:
        raise HTTPException(401, "Falta el token del agente.")
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(404, "El enlace del agente no es valido.")

Token = Annotated[UUID, Depends(agent_token)]

def require_agent(db, token):
    rows = db.table("agentes").select("id,nombre,especialidad").eq("token_uuid", str(token)).limit(2).execute().data
    if not rows:
        raise HTTPException(404, "El enlace del agente no es valido.")
    if len(rows) != 1:
        raise HTTPException(503, "El token del agente no es unico. Revisa la configuracion.")
    agent = rows[0]
    if not agent.get("especialidad") or not agent["especialidad"].strip():
        raise HTTPException(403, "El agente no tiene una especialidad configurada.")
    return agent

@router.get("/api/agentes/contexto", summary="Validar acceso del agente")
def context(token: Token, db=Depends(get_db)):
    agent = require_agent(db, token)
    return {"nombre": agent["nombre"], "especialidad": agent["especialidad"]}

@router.get("/api/agentes/visitas", summary="Solicitudes de visita de la especialidad del agente")
def visits(token: Token, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=60), db=Depends(get_db)):
    agent = require_agent(db, token)
    rows = (db.table("visitas").select(
        "id,fecha_cliente,fecha_agente,fecha_acordada,created_at,"
        "estados_visita!inner(nombre),"
        "propiedades!visitas_propiedad_id_fkey!inner(id,titulo,tipo_inmueble,tipo_operacion,direccion,distritos(nombre)),"
        "oportunidades!visitas_oportunidad_id_fkey!inner(resultado,fecha_cierre,leads!inner(nombre,telefono))")
        .eq("propiedades.tipo_inmueble", agent["especialidad"])
        .eq("estados_visita.nombre", get_settings().initial_visit_state)
        .is_("oportunidades.resultado", "null").is_("oportunidades.fecha_cierre", "null")
        .order("fecha_cliente", nullsfirst=False).order("id").range(offset, offset + limit - 1).execute().data)
    result = []
    for row in rows:
        opportunity = row.pop("oportunidades")
        row["cliente"] = opportunity["leads"]
        result.append(row)
    return result

@router.get("/agente/{token_uuid}", response_class=FileResponse, summary="Abrir el panel de visitas del agente")
def page(token_uuid: UUID, db=Depends(get_db)):
    try:
        require_agent(db, token_uuid)
    except HTTPException as error:
        if error.status_code in (403, 404):
            return FileResponse(ROOT / "static/acceso-invalido.html", status_code=error.status_code)
        raise
    return FileResponse(ROOT / "app/templates/agente_visitas.html")
