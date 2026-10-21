from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal['vista_1', 'vista_2', 'plano']


class PropertyWrite(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)
    titulo: str | None = Field(None, max_length=200)
    descripcion: str | None = Field(None, max_length=15000)
    tipo_operacion: str | None = Field(None, max_length=80)
    tipo_inmueble: str | None = Field(None, max_length=100)
    condicion: str | None = Field(None, max_length=100)
    proyecto: str | None = Field(None, max_length=200)
    distrito_id: int | None = Field(None, gt=0)
    moneda: str | None = Field(None, max_length=12)
    precio: Decimal | None = Field(None, ge=0, max_digits=16, decimal_places=2)
    cantidad_dormitorios: int | None = Field(None, ge=0, le=1000)
    cantidad_banos: int | None = Field(None, ge=0, le=1000)
    cocheras: int | None = Field(None, ge=0, le=1000)
    area_total: Decimal | None = Field(None, gt=0, max_digits=16, decimal_places=2)
    direccion: str | None = Field(None, max_length=500)
    disponible: bool | None = None
    agente_id: int | None = Field(None, gt=0)

    @field_validator('titulo','descripcion','tipo_operacion','tipo_inmueble','condicion','proyecto','moneda','direccion', mode='before')
    @classmethod
    def blank_to_null(cls, value):
        return None if isinstance(value,str) and not value.strip() else value


class AvailabilityIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    disponible: bool


class ImageOrderIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ids: list[int] = Field(max_length=1000)

    @field_validator('ids')
    @classmethod
    def unique_positive_ids(cls, value):
        if any(i<=0 for i in value) or len(set(value))!=len(value):
            raise ValueError('Indica IDs positivos sin repetir.')
        return value
