from ninja import Router
from core.security import secretario_auth
from academico.schemas import MensajeOut # Reutilizamos el esquema genérico
from .schemas import ConfiguracionOut, ConfiguracionUpdateIn
from .services import obtener_configuracion

# Aplicamos la seguridad estricta a todo el router
router = Router(tags=["Configuración Global"], auth=secretario_auth)

@router.get("/", response=ConfiguracionOut)
def ver_configuracion(request):
    """
    Devuelve los parámetros actuales del sistema (Tolerancia GPS, WiFi, etc).
    """
    return obtener_configuracion()

@router.patch("/", response={200: ConfiguracionOut, 400: MensajeOut})
def actualizar_configuracion(request, payload: ConfiguracionUpdateIn):
    """
    Actualiza parámetros específicos de la configuración global.
    """
    config = obtener_configuracion()
    datos = payload.dict(exclude_unset=True)

    if 'latitud_campus' in datos and not (-90 <= datos['latitud_campus'] <= 90):
        return 400, {"success": False, "mensaje": "La latitud debe estar entre -90 y 90."}

    if 'longitud_campus' in datos and not (-180 <= datos['longitud_campus'] <= 180):
        return 400, {"success": False, "mensaje": "La longitud debe estar entre -180 y 180."}

    if 'radio_gps_metros' in datos and not (50 <= datos['radio_gps_metros'] <= 5000):
        return 400, {"success": False, "mensaje": "El radio GPS debe estar entre 50 y 5000 metros."}

    if 'metodo_validacion_ubicacion' in datos:
        from core.constants import MetodoValidacion
        valores_validos = {choice[0] for choice in MetodoValidacion.choices}
        if datos['metodo_validacion_ubicacion'] not in valores_validos:
            return 400, {"success": False, "mensaje": "Método de validación de ubicación inválido."}

    for attr, value in datos.items():
        setattr(config, attr, value)

    config.modificado_por = request.user
    config.save()

    return 200, config