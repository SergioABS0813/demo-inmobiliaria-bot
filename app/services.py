from datetime import timedelta, timezone
from hashlib import sha256
import json
from fastapi import HTTPException
from .config import get_settings

LIMA = timezone(timedelta(hours=-5), "America/Lima")


def require_lead(db, token):
    rows = db.table("leads").select("id,nombre,consentimiento").eq("token_uuid", str(token)).limit(2).execute().data
    if not rows:
        raise HTTPException(404, "El enlace no es válido. Solicita uno nuevo por WhatsApp.")
    if len(rows) != 1:
        raise HTTPException(503, "No se puede resolver este enlace de forma segura.")
    return rows[0]


def validate_timezone(value):
    if value.tzinfo is None or value.utcoffset() != timedelta(hours=-5):
        raise HTTPException(422, "La fecha debe incluir la zona horaria de Lima (-05:00).")


def request_fingerprint(body):
    data = body.model_dump(mode="json", exclude={"request_id"})
    data["fecha_cliente"] = body.fecha_cliente.astimezone(timezone.utc).isoformat()
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def create_visit(db, token, body):
    # Token resolution and the first checks give useful errors; the RPC checks again
    # under locks and atomically writes lead + consent + visit.
    require_lead(db, token)
    if not body.consentimiento:
        raise HTTPException(422, "Autoriza el uso de tus datos para gestionar esta solicitud.")
    validate_timezone(body.fecha_cliente)
    # Future-date validation is inside the RPC, AFTER replay lookup. A retry of
    # an already accepted request must work even after its requested time passes.
    result = db.rpc("ru_solicitar_visita", {
        "p_token": str(token), "p_propiedad_id": body.propiedad_id,
        "p_nombre": body.nombre, "p_fecha": body.fecha_cliente.isoformat(),
        "p_consentimiento": body.consentimiento, "p_request_id": str(body.request_id),
        "p_request_hash": request_fingerprint(body),
        "p_estado_nombre": get_settings().initial_visit_state,
    }).execute().data
    return result


def normalize_property(row):
    district = row.pop("distritos", None)
    row["distrito"] = district.get("nombre") if district else None
    row["imagenes"] = sorted(row.pop("propiedad_imagenes", []) or [], key=lambda i: (i.get("orden") is None, i.get("orden") or 0, i["id"]))
    return row


