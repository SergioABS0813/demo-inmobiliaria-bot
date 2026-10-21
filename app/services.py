from datetime import timedelta, timezone
from hashlib import sha256
import json
from fastapi import HTTPException
from .config import get_settings

LIMA = timezone(timedelta(hours=-5), "America/Lima")


def require_opportunity(db, token):
    """The capability belongs to an OPEN opportunity, never to leads."""
    rows = (db.table("oportunidades")
            .select("id,lead_id,estado_id,resultado,fecha_cierre,leads(id,nombre,telefono),estado_oportunidad(nombre)")
            .eq("token_uuid", str(token)).limit(2).execute().data)
    if not rows:
        raise HTTPException(404, "El enlace no es válido. Solicita uno nuevo por WhatsApp.")
    if len(rows) != 1:
        raise HTTPException(503, "No se puede resolver este enlace de forma segura.")
    opportunity = rows[0]
    if opportunity["resultado"] is not None or opportunity["fecha_cierre"] is not None:
        raise HTTPException(403, "Esta oportunidad ya está cerrada. Solicita un nuevo enlace por WhatsApp.")
    if not opportunity.get("lead_id") or not opportunity.get("leads") or not opportunity.get("estado_oportunidad"):
        raise HTTPException(503, "La oportunidad no está configurada correctamente.")
    return opportunity


def current_visit(db, opportunity_id):
    rows = db.table("visitas").select("id,request_id,request_hash").eq("oportunidad_id", opportunity_id).limit(2).execute().data
    if len(rows) > 1:
        raise HTTPException(503, "La oportunidad tiene solicitudes inconsistentes.")
    return rows[0] if rows else None


def existing_visit_error(visit_id):
    return HTTPException(409, {"code": "visita_existente", "mensaje": "Ya solicitaste una visita para esta oportunidad. Puedes consultar tu solicitud existente.", "visita_id": visit_id})


def validate_timezone(value):
    if value.tzinfo is None or value.utcoffset() != timedelta(hours=-5):
        raise HTTPException(422, "La fecha debe incluir la zona horaria de Lima (-05:00).")


def request_fingerprint(body):
    data = body.model_dump(mode="json", exclude={"request_id"})
    data["fecha_cliente"] = body.fecha_cliente.astimezone(timezone.utc).isoformat()
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def create_visit(db, token, body):
    opportunity = require_opportunity(db, token)
    if not body.consentimiento:
        raise HTTPException(422, "Autoriza el uso de tus datos para gestionar esta solicitud.")
    validate_timezone(body.fecha_cliente)
    fingerprint = request_fingerprint(body)
    existing = current_visit(db, opportunity["id"])
    if existing:
        if str(existing.get("request_id")) == str(body.request_id):
            if existing.get("request_hash") != fingerprint:
                raise HTTPException(409, "Esta clave de solicitud ya se utilizó con otros datos.")
            return {"id": existing["id"], "replayed": True}
        raise existing_visit_error(existing["id"])
    # Future-date validation is inside the RPC, AFTER replay lookup. A retry of
    # an already accepted request must work even after its requested time passes.
    result = db.rpc("ru_solicitar_visita_oportunidad", {
        "p_token": str(token), "p_propiedad_id": body.propiedad_id,
        "p_nombre": body.nombre, "p_fecha": body.fecha_cliente.isoformat(),
        "p_consentimiento": body.consentimiento, "p_request_id": str(body.request_id),
        "p_request_hash": fingerprint,
        "p_estado_nombre": get_settings().initial_visit_state,
        "p_estado_oportunidad": get_settings().requested_opportunity_state,
    }).execute().data
    return result


def normalize_property(row):
    row["titulo"] = row.get("titulo") or "Inmueble sin título"
    row["tipo_operacion"] = row.get("tipo_operacion") or "Por consultar"
    row["tipo_inmueble"] = row.get("tipo_inmueble") or "Por consultar"
    row["moneda"] = row.get("moneda") or ""
    row["disponible"] = bool(row.get("disponible"))
    district = row.pop("distritos", None)
    row["distrito"] = district.get("nombre") if district else None
    row["imagenes"] = sorted(row.pop("propiedad_imagenes", []) or [], key=lambda i: (i.get("orden") is None, i.get("orden") or 0, i["id"]))
    return row


