from ninja import Schema


class ErrorValidacionOut(Schema):
    """Detalle de un error de validación detectado durante la importación."""
    hoja: str
    fila: int
    columna: str
    valor_recibido: str
    mensaje: str


class InicioImportacionOut(Schema):
    """Respuesta al iniciar una importación (para SSE tracking)."""
    task_id: str
    mensaje: str


class ResumenImportacionOut(Schema):
    """Resumen final de una importación completada exitosamente."""
    success: bool
    docentes_creados: int
    docentes_actualizados: int
    carreras_creadas: int
    carreras_actualizadas: int
    materias_creadas: int
    materias_actualizadas: int
    horarios_creados: int
    asignaciones_creadas: int
    asignaciones_actualizadas: int
    materia_carrera_creadas: int
    materia_carrera_actualizadas: int