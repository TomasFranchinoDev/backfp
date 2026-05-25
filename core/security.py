from ninja.security import django_auth
from django.http import HttpRequest
from usuarios.services import obtener_rol_usuario

def secretario_auth(request: HttpRequest):
    """
    Dependencia de seguridad para Django Ninja.
    1. Verifica que el usuario tenga una sesión activa.
    2. Verifica que su rol activo sea 'secretario' (o superadmin).
    Si falla, Ninja devuelve un error 401 Unauthorized automáticamente.
    """
    # Usamos la validación nativa de sesión primero
    user = django_auth(request)
    if not user:
        return None
        
    rol = obtener_rol_usuario(user)
    if rol in ['secretario', 'admin']:
        return user
        
    return None  # Está logueado, pero no tiene permisos

def docente_auth(request: HttpRequest):
    """
    Dependencia para endpoints exclusivos de docentes (como el fichaje).
    """
    user = django_auth(request)
    if not user:
        return None
        
    rol = obtener_rol_usuario(user)
    if rol in ['docente', 'admin']:
        return user
        
    return None