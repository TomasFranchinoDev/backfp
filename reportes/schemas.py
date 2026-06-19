from ninja import Schema
from typing import List, Optional
from datetime import date

class DetalleAusenciaOut(Schema):
    fecha: date
    materia_nombre: str
    docente_nombre: Optional[str] = None
    dia_semana: str
    hora_inicio: str
    evento_calendario: Optional[str] = None

class ResumenFilaOut(Schema):
    id: int
    codigo: Optional[str] = None
    nombre: str
    total_clases_esperadas: int
    total_asistencias: int
    total_ausencias: int
    detalle_ausencias: List[DetalleAusenciaOut]

class ReporteMensualOut(Schema):
    desde: date
    hasta: date
    institucion: Optional[str] = None
    agrupar_por: str
    resultados: List[ResumenFilaOut]