"""
Almacén de progreso en base de datos para tareas de importación.

Soporta acceso concurrente desde múltiples workers y endpoints SSE.
Las tareas se pueden limpiar periódicamente.
"""
import json
import uuid
from datetime import timedelta
from typing import Optional

from django.utils import timezone
from .models import ImportTask

_EXPIRY_SECONDS = 300  # 5 minutos


def crear_tarea() -> str:
    """Crea una nueva tarea de importación en la base de datos y devuelve su ID."""
    task_id = str(uuid.uuid4())
    ImportTask.objects.create(task_id=task_id)
    return task_id


def actualizar_progreso(
    task_id: str,
    *,
    estado: Optional[str] = None,
    fase: Optional[str] = None,
    paso: Optional[str] = None,
    progreso: Optional[int] = None,
):
    """Actualiza parcialmente el progreso de una tarea existente."""
    try:
        task = ImportTask.objects.get(task_id=task_id)
        if estado is not None:
            task.estado = estado
        if fase is not None:
            task.fase = fase
        if paso is not None:
            task.paso = paso
        if progreso is not None:
            task.progreso = progreso
        # El timestamp se actualiza automáticamente por auto_now=True
        task.save()
    except ImportTask.DoesNotExist:
        pass


def completar_tarea(task_id: str, resultado: dict):
    """Marca una tarea como completada exitosamente con su resumen."""
    try:
        task = ImportTask.objects.get(task_id=task_id)
        task.estado = "completado"
        task.fase = "completado"
        task.paso = "Importación finalizada exitosamente"
        task.progreso = 100
        task.resultado = resultado
        task.save()
    except ImportTask.DoesNotExist:
        pass


def error_validacion_tarea(task_id: str, errores: list[dict]):
    """Marca una tarea como fallida por errores de validación."""
    try:
        task = ImportTask.objects.get(task_id=task_id)
        task.estado = "error_validacion"
        task.fase = "validacion"
        task.paso = f"Se encontraron {len(errores)} error(es) de validación"
        task.progreso = 100
        task.errores = errores
        task.save()
    except ImportTask.DoesNotExist:
        pass


def error_sistema_tarea(task_id: str, mensaje: str):
    """Marca una tarea como fallida por un error interno del sistema."""
    try:
        task = ImportTask.objects.get(task_id=task_id)
        task.estado = "error_sistema"
        task.fase = "error"
        task.paso = mensaje
        task.progreso = 100
        task.errores = None
        task.save()
    except ImportTask.DoesNotExist:
        pass


def obtener_progreso(task_id: str) -> Optional[dict]:
    """Devuelve una copia del estado actual de una tarea, o None si no existe."""
    try:
        task = ImportTask.objects.get(task_id=task_id)
        return {
            "estado": task.estado,
            "fase": task.fase,
            "paso": task.paso,
            "progreso": task.progreso,
            "resultado": task.resultado,
            "errores": task.errores,
        }
    except ImportTask.DoesNotExist:
        return None


def limpiar_tareas_expiradas():
    """Elimina tareas que llevan más de _EXPIRY_SECONDS sin actualizarse."""
    limit_time = timezone.now() - timedelta(seconds=_EXPIRY_SECONDS)
    ImportTask.objects.filter(timestamp__lt=limit_time).delete()


def formato_sse(data: dict) -> str:
    """Formatea un diccionario como evento SSE (Server-Sent Events)."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
