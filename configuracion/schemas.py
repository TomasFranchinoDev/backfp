from ninja import ModelSchema, Schema
from typing import Optional
from .models import Configuracion

class ConfiguracionOut(ModelSchema):
    class Meta:
        model = Configuracion
        fields = [
            'id',
            'dia_corte_mensual',
            'red_wifi_campus',
            'metodo_validacion_ubicacion',
            'latitud_campus',
            'longitud_campus',
            'radio_gps_metros',
        ]


class ConfiguracionUpdateIn(Schema):
    dia_corte_mensual: Optional[int] = None
    red_wifi_campus: Optional[str] = None
    metodo_validacion_ubicacion: Optional[str] = None
    latitud_campus: Optional[float] = None
    longitud_campus: Optional[float] = None
    radio_gps_metros: Optional[int] = None