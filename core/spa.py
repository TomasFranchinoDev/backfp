import os

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound


def spa_index(request):
    """
    Vista catch-all que sirve el index.html del frontend React.

    WhiteNoise se encarga de servir los archivos estáticos (JS, CSS, imágenes)
    desde la carpeta dist/. Esta vista solo maneja las rutas del SPA
    (ej: /login, /secretario/dashboard, /docente/asincronica) devolviendo
    el index.html para que React Router resuelva la ruta del lado del cliente.
    """
    index_path = os.path.join(settings.BASE_DIR, 'dist', 'index.html')

    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            return HttpResponse(f.read(), content_type='text/html')
    except FileNotFoundError:
        return HttpResponseNotFound(
            '<h1>Frontend no disponible</h1>'
            '<p>El build del frontend no fue encontrado en dist/index.html</p>',
            content_type='text/html',
        )
