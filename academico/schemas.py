from ninja import ModelSchema, Schema
from typing import List, Optional
from datetime import date
from .models import Carrera, Materia, SlotHorario

# --- CARRERAS ---
class CarreraIn(ModelSchema):
    class Meta:
        model = Carrera
        fields = ['institucion', 'codigo', 'nombre', 'duracion_anios']

class CarreraOut(ModelSchema):
    class Meta:
        model = Carrera
        fields = ['id', 'institucion', 'codigo', 'nombre', 'duracion_anios']

# --- MATERIAS ---
class CarreraResumenOut(Schema):
    id: int
    codigo: str
    nombre: str


class MateriaIn(Schema):
    codigo_siu: str
    nombre: str
    anio: int
    activa: bool = True
    carreras_ids: List[int]


class MateriaOut(Schema):
    id: int
    codigo_siu: str
    nombre: str
    anio: int
    activa: bool
    carreras: List[CarreraResumenOut]
    desactivada_en: Optional[date] = None

# --- SLOTS HORARIOS ---
class SlotHorarioIn(ModelSchema):
    materia_id: int

    class Meta:
        model = SlotHorario
        fields = ['dia_semana', 'hora_inicio', 'hora_fin']

class SlotHorarioOut(ModelSchema):
    materia_id: int # Sobreescribimos ligeramente para que devuelva el ID y no el objeto completo
    
    class Meta:
        model = SlotHorario
        fields = ['id', 'dia_semana', 'hora_inicio', 'hora_fin']

# Esquema genérico para respuestas de éxito/error
class MensajeOut(Schema):
    success: bool
    mensaje: str