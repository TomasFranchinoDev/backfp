import math
from dataclasses import dataclass
from typing import Optional
from core.constants import MetodoValidacion


@dataclass
class ResultadoValidacionUbicacion:
    """Resultado desglosado de la validación de ubicación."""
    ubicacion_ok: bool
    gps_ok: Optional[bool]    # None si no se enviaron coordenadas
    wifi_ok: Optional[bool]   # None si no hay red configurada
    mensaje: str


def calcular_distancia_metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula la distancia en metros entre dos coordenadas usando Haversine."""
    R = 6371000 # Radio de la Tierra en metros
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def validar_ubicacion(lat_docente: float, lon_docente: float, ip_registrada: str, config) -> ResultadoValidacionUbicacion:
    """
    Evalúa la ubicación del docente contra las reglas configuradas en el sistema.
    Retorna un ResultadoValidacionUbicacion con el desglose de GPS y WiFi.
    """
    metodo = config.metodo_validacion_ubicacion
    
    # 1. Chequeo por WiFi (usamos la IP pública o rango de red interna)
    # Nota: Acá asumimos que config.red_wifi_campus guarda la IP estática de salida de ICES
    wifi_ok: Optional[bool] = None
    if config.red_wifi_campus:
        wifi_ok = (ip_registrada == config.red_wifi_campus)

    # 2. Chequeo por GPS (coordenadas y radio desde configuración global)
    gps_ok: Optional[bool] = None
    if lat_docente and lon_docente:
        lat_campus = float(config.latitud_campus)
        lon_campus = float(config.longitud_campus)
        radio_metros = int(config.radio_gps_metros)
        distancia = calcular_distancia_metros(lat_campus, lon_campus, lat_docente, lon_docente)
        gps_ok = distancia <= radio_metros

    # Valores booleanos seguros para la lógica de reglas
    en_radio_gps = gps_ok is True
    en_wifi_institucional = wifi_ok is True

    # 3. Aplicar la regla de negocio estricta
    if metodo == MetodoValidacion.SOLO_WIFI:
        if not en_wifi_institucional:
            return ResultadoValidacionUbicacion(
                ubicacion_ok=False, gps_ok=gps_ok, wifi_ok=wifi_ok,
                mensaje="Debés estar conectado a la red WiFi de la institución."
            )
            
    elif metodo == MetodoValidacion.SOLO_GPS:
        if not en_radio_gps:
            return ResultadoValidacionUbicacion(
                ubicacion_ok=False, gps_ok=gps_ok, wifi_ok=wifi_ok,
                mensaje="Estás fuera del radio geográfico permitido por la institución."
            )
            
    elif metodo == MetodoValidacion.GPS_O_WIFI:
        if not en_wifi_institucional and not en_radio_gps:
            return ResultadoValidacionUbicacion(
                ubicacion_ok=False, gps_ok=gps_ok, wifi_ok=wifi_ok,
                mensaje="Debés estar en el campus (Conectado al WiFi o dentro del radio GPS)."
            )

    return ResultadoValidacionUbicacion(
        ubicacion_ok=True, gps_ok=gps_ok, wifi_ok=wifi_ok,
        mensaje="Ubicación validada correctamente."
    )