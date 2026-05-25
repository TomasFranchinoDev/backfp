from ninja import ModelSchema, Schema

from .models import AsignacionDocente

class AsignacionDocenteIn(ModelSchema):
    class Meta:
        model = AsignacionDocente
        fields = ['docente', 'materia', 'rol', 'fecha_inicio', 'fecha_fin']

class AsignacionDocenteOut(ModelSchema):
    docente_id: int
    materia_id: int
    
    class Meta:
        model = AsignacionDocente
        fields = ['id', 'rol', 'activa', 'fecha_inicio', 'fecha_fin']

# Esquema para devolver la materia y slot sugeridos al escanear
class SugerenciaEscaneoOut(Schema):
    materia_id: int
    materia_nombre: str
    slot_id: int
    hora_inicio: str
    hora_fin: str