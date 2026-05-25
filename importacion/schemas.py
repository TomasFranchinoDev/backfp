from ninja import Schema

class RegistroError(Schema):
    pestana: str
    fila: int
    error: str

class ResumenImportacionOut(Schema):
    success: bool
    carreras_creadas: int
    materias_creadas: int
    docentes_creados: int
    horarios_creados: int
    asignaciones_creadas: int
    errores: list[RegistroError]