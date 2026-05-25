from .models import Usuario

def obtener_rol_usuario(user: Usuario) -> str:
    """Deduce el rol principal del usuario basándose en sus perfiles."""
    if user.is_superuser:
        return 'admin'
    if hasattr(user, 'secretario') and user.secretario.activo:
        return 'secretario'
    if hasattr(user, 'docente') and user.docente.activo:
        return 'docente'
    return 'sin_rol'