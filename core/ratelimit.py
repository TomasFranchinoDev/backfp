"""
Adaptador de django-ratelimit para Django Ninja.

Provee decoradores tipados por tier de protección que se aplican
directamente sobre las funciones de vista de Ninja.

Tiers:
  - T1 (brute_force): 5/min por IP  → login, CSRF
  - T2 (heavy_ops):   3/min por usuario → importación, reportes
"""
import logging
from functools import wraps

from django.http import JsonResponse
from django_ratelimit.decorators import ratelimit as dj_ratelimit

logger = logging.getLogger(__name__)

# ─── Constantes centralizadas ────────────────────────────────────────────────
RATE_BRUTE_FORCE = "5/m"   # Tier 1: Login, CSRF
RATE_HEAVY_OPS = "3/m"     # Tier 2: Importación, reportes


def _build_429_response(tier: str) -> JsonResponse:
    """Construye una respuesta 429 estandarizada."""
    return JsonResponse(
        {
            "success": False,
            "mensaje": "Demasiadas solicitudes. Por favor, esperá unos momentos antes de reintentar.",
        },
        status=429,
    )


def ninja_ratelimit(rate: str, key: str = "ip", tier_name: str = "standard"):
    """
    Decorador de rate limiting compatible con Django Ninja.

    Envuelve la función de vista para aplicar django-ratelimit y
    verificar request.limited antes de ejecutar la lógica del endpoint.
    """
    def decorator(view_func):
        @dj_ratelimit(key=key, rate=rate)
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if getattr(request, "limited", False):
                logger.warning(
                    "Rate limit excedido [tier=%s, rate=%s, ip=%s, user=%s, path=%s]",
                    tier_name,
                    rate,
                    request.META.get("REMOTE_ADDR"),
                    getattr(request.user, "username", "anon"),
                    request.path,
                )
                return _build_429_response(tier_name)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ─── Decoradores pre-configurados por tier ───────────────────────────────────

def ratelimit_brute_force(view_func):
    """Tier 1: Protección contra fuerza bruta. 5/min por IP."""
    return ninja_ratelimit(
        rate=RATE_BRUTE_FORCE, key="ip", tier_name="brute_force"
    )(view_func)


def ratelimit_heavy_ops(view_func):
    """Tier 2: Protección contra DoS de operaciones pesadas. 3/min por usuario."""
    return ninja_ratelimit(
        rate=RATE_HEAVY_OPS, key="user", tier_name="heavy_ops"
    )(view_func)
