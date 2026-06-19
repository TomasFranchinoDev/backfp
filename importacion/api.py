import asyncio
import io
import logging
import threading

from django.http import HttpResponse, StreamingHttpResponse
from ninja import File, Router
from ninja.files import UploadedFile

from core.security import secretario_auth

from .plantilla import generar_plantilla_excel
from .progress import (
    crear_tarea,
    formato_sse,
    limpiar_tareas_expiradas,
    obtener_progreso,
)
from .schemas import InicioImportacionOut
from .services import procesar_importacion

router = Router(tags=["Importación SIU"], auth=secretario_auth)
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# GET /importacion/plantilla — Descarga de plantilla dinámica
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/plantilla")
def descargar_plantilla(request):
    """Genera y devuelve la plantilla Excel de importación."""
    buf = generar_plantilla_excel()
    response = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        'attachment; filename="plantilla_importacion_siu.xlsx"'
    )
    return response


# ─────────────────────────────────────────────────────────────────────────────
# POST /importacion/siu — Subir archivo e iniciar importación
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/siu", response={200: InicioImportacionOut, 400: dict})
def subir_archivo_siu(request, file: UploadedFile = File(...)):
    """Recibe un Excel, lo valida de forma básica y lanza el procesamiento
    en un hilo de fondo.  Devuelve un ``task_id`` para seguir el progreso
    vía SSE."""

    # Validar extensión
    if not file.name.endswith((".xlsx", ".xls")):
        return 400, {"mensaje": "El archivo debe ser un Excel (.xlsx o .xls)"}

    # Validar tamaño
    if file.size > MAX_FILE_SIZE:
        return 400, {"mensaje": "Archivo demasiado grande (máximo 5 MB)"}

    # Leer contenido en memoria
    file.file.seek(0)
    file_bytes = file.file.read()
    user_id = request.user.id

    # Crear tarea y lanzar hilo de procesamiento
    limpiar_tareas_expiradas()
    task_id = crear_tarea()

    thread = threading.Thread(
        target=procesar_importacion,
        args=(io.BytesIO(file_bytes), user_id, task_id),
        daemon=True,
    )
    thread.start()

    return 200, InicioImportacionOut(
        task_id=task_id,
        mensaje="Importación iniciada. Conecte al endpoint de progreso para seguimiento.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /importacion/progreso/{task_id} — SSE de progreso
# ─────────────────────────────────────────────────────────────────────────────

ESTADOS_TERMINALES = {"completado", "error_validacion", "error_sistema"}


@router.get("/progreso/{task_id}")
async def progreso_importacion(request, task_id: str):
    """Endpoint Server-Sent Events (SSE) que transmite el progreso de una
    importación en tiempo real.  Requiere ASGI (Uvicorn)."""

    async def event_stream():
        intentos_vacios = 0
        while True:
            progress = obtener_progreso(task_id)

            if progress is None:
                intentos_vacios += 1
                if intentos_vacios > 10:
                    yield formato_sse({
                        "estado": "no_encontrado",
                        "progreso": 0,
                        "paso": "Tarea no encontrada",
                    })
                    break
                await asyncio.sleep(0.5)
                continue

            intentos_vacios = 0
            # No enviar el timestamp interno
            progress.pop("timestamp", None)
            yield formato_sse(progress)

            if progress.get("estado") in ESTADOS_TERMINALES:
                break

            await asyncio.sleep(0.5)

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response