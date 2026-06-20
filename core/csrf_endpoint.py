from ninja import Router
from django.http import HttpRequest
from django.middleware.csrf import get_token
from core.ratelimit import ratelimit_brute_force

router = Router(tags=["CSRF"])


@router.get("/token")
@ratelimit_brute_force
def obtener_csrf_token(request: HttpRequest):
    """
    Endpoint para obtener el CSRF token en despliegues cross-origin.
    
    Cuando el frontend (Vercel) y el backend (Railway) están en dominios
    diferentes, JavaScript no puede leer la cookie csrftoken del otro dominio
    debido a la Same-Origin Policy del navegador.
    
    Este endpoint devuelve el token en el body JSON para que el frontend
    pueda incluirlo en el header X-CSRFToken de las peticiones POST/PUT/PATCH/DELETE.
    """
    token = get_token(request)
    return {"csrftoken": token}
