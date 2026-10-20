from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class VisitIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    propiedad_id: int = Field(gt=0)
    nombre: str = Field(min_length=3, max_length=120)
    fecha_cliente: datetime
    consentimiento: bool
    request_id: UUID

    @field_validator("nombre")
    @classmethod
    def valid_name(cls, value):
        if any(ord(c) < 32 for c in value) or not any(c.isalpha() for c in value):
            raise ValueError("Indica un nombre válido.")
        return value


class OpportunityContextOut(BaseModel):
    nombre: str | None
    estado_oportunidad: str
    visita_id: int | None
    puede_solicitar: bool
    privacy_contact: str


class VisitCreatedOut(BaseModel):
    id: int
    replayed: bool


class VisitOut(BaseModel):
    id: int
    oportunidad_id: int
    fecha_cliente: datetime | None = None
    fecha_agente: datetime | None = None
    fecha_acordada: datetime | None = None
    estado_id: int | None = None
    estados_visita: dict | None = None
    propiedades: dict | None = None
    es_oportunidad_actual: bool


class PropertyOut(BaseModel):
    id: int
    titulo: str
    descripcion: str | None = None
    tipo_operacion: str
    tipo_inmueble: str
    condicion: str | None = None
    proyecto: str | None = None
    distrito: str | None = None
    distrito_id: int | None = None
    moneda: str
    precio: Decimal | None
    cantidad_dormitorios: int | None = None
    cantidad_banos: int | None = None
    cocheras: int | None = None
    area_total: Decimal | None = None
    direccion: str | None = None
    disponible: bool
    imagenes: list[dict] = Field(default_factory=list)
