"""
Almacén de progreso en memoria para tareas de importación.

Soporta acceso concurrente desde hilos de procesamiento y endpoints SSE.
Las tareas expiran automáticamente después de 5 minutos.
"""
import json
import threading
import time
import uuid
from typing import Optional

_store: dict[str, dict] = {}
_lock = threading.Lock()
_EXPIRY_SECONDS = 300  # 5 minutos


def crear_tarea() -> str:
    """Crea una nueva tarea de importación y devuelve su ID."""
    task_id = str(uuid.uuid4())
    with _lock:
        _store[task_id] = {
            "estado": "iniciado",
            "fase": "",
            "paso": "",
            "progreso": 0,
            "resultado": None,
            "errores": None,
            "timestamp": time.time(),
        }
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
    with _lock:
        if task_id not in _store:
            return
        entry = _store[task_id]
        if estado is not None:
            entry["estado"] = estado
        if fase is not None:
            entry["fase"] = fase
        if paso is not None:
            entry["paso"] = paso
        if progreso is not None:
            entry["progreso"] = progreso
        entry["timestamp"] = time.time()


def completar_tarea(task_id: str, resultado: dict):
    """Marca una tarea como completada exitosamente con su resumen."""
    with _lock:
        if task_id not in _store:
            return
        _store[task_id].update({
            "estado": "completado",
            "fase": "completado",
            "paso": "Importación finalizada exitosamente",
            "progreso": 100,
            "resultado": resultado,
            "timestamp": time.time(),
        })


def error_validacion_tarea(task_id: str, errores: list[dict]):
    """Marca una tarea como fallida por errores de validación."""
    with _lock:
        if task_id not in _store:
            return
        _store[task_id].update({
            "estado": "error_validacion",
            "fase": "validacion",
            "paso": f"Se encontraron {len(errores)} error(es) de validación",
            "progreso": 100,
            "errores": errores,
            "timestamp": time.time(),
        })


def error_sistema_tarea(task_id: str, mensaje: str):
    """Marca una tarea como fallida por un error interno del sistema."""
    with _lock:
        if task_id not in _store:
            return
        _store[task_id].update({
            "estado": "error_sistema",
            "fase": "error",
            "paso": mensaje,
            "progreso": 100,
            "errores": None,
            "timestamp": time.time(),
        })


def obtener_progreso(task_id: str) -> Optional[dict]:
    """Devuelve una copia del estado actual de una tarea, o None si no existe."""
    with _lock:
        entry = _store.get(task_id)
        return dict(entry) if entry else None


def limpiar_tareas_expiradas():
    """Elimina tareas que llevan más de _EXPIRY_SECONDS sin actualizarse."""
    now = time.time()
    with _lock:
        expired = [k for k, v in _store.items() if now - v["timestamp"] > _EXPIRY_SECONDS]
        for k in expired:
            del _store[k]


def formato_sse(data: dict) -> str:
    """Formatea un diccionario como evento SSE (Server-Sent Events)."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
