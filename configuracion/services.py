from .models import Configuracion

def obtener_configuracion() -> Configuracion:
    """
    Recupera la configuración global del sistema (Singleton).
    Si no existe (ej. primer inicio del sistema), la crea.
    """
    config, created = Configuracion.objects.get_or_create(id=1)
    return config