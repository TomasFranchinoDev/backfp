from ninja import Schema
from typing import Optional
from datetime import date, datetime

class FichajeEntradaIn(Schema):
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    tipo_clase: str = 'presencial' # Puede enviar 'asincronica' o 'virtual_sincronica'

class FichajeOut(Schema):
    """Respuesta simple para endpoints que no requieren desglose (emergencias, asincrónica)."""
    success: bool
    mensaje: str

class FichajeRichOut(Schema):
    """Respuesta enriquecida para entrada y salida con desglose de validaciones."""
    success: bool
    estado_flujo: str          # "exito", "error_gps", "error_wifi", "error_ubicacion",
                               # "error_horario", "duplicado", "sin_clases"
    gps_ok: Optional[bool] = None
    wifi_ok: Optional[bool] = None
    materia: Optional[str] = None
    docente_nombre: Optional[str] = None
    hora_fichada: Optional[str] = None
    tipo_clase: Optional[str] = None
    mensaje: str

class ProximaClaseOut(Schema):
    """Información de la próxima clase fichable del día."""
    materia_nombre: str
    hora_inicio: str
    hora_fin: str
    fichable_desde: str        # hora_inicio - margen configurado

class EstadoFichajeOut(Schema):
    tiene_entrada_activa: bool
    materia_actual: Optional[str] = None
    hora_entrada: Optional[str] = None
    # --- Campos nuevos (todos opcionales → retrocompatible) ---
    clase_vigente: Optional[str] = None                    # Nombre de materia en ventana actual
    proxima_clase: Optional[ProximaClaseOut] = None        # Siguiente clase del día si no hay vigente
    metodo_validacion: Optional[str] = None                # "gps_o_wifi" | "solo_gps" | "solo_wifi"


# --- EMERGENCIAS ---

class SolicitudEmergenciaIn(Schema):
    slot_horario_id: Optional[int] = None
    nota_docente: str
    fecha: Optional[date] = None

class SolicitudEmergenciaOut(Schema):
    id: int
    docente_nombre: str
    materia_nombre: str
    fecha: date
    estado: str
    nota_docente: str

class SolicitudEmergenciaHistorialOut(Schema):
    id: int
    docente_nombre: str
    materia_nombre: str
    fecha: date
    estado: str
    nota_docente: str
    nota_secretaria: str
    revisado_por_nombre: Optional[str] = None
    revisado_en: Optional[datetime] = None

class ResolverEmergenciaIn(Schema):
    aprobar: bool
    nota_secretaria: str

class ClaseDisponibleOut(Schema):
    slot_id: int
    carreras_codigos: str
    materia_nombre: str
    hora_inicio: str
    hora_fin: str

class DeclaracionAsincronicaIn(Schema):
    slot_horario_id: int
    fecha_dictado: date  # El docente elige el día (generalmente "hoy")
    nota: str = ""       # Ej: "Dejé el TP en el campus virtual"

class HistorialClaseOut(Schema):
    fecha: str
    tipo: str
    estado: str
    detalle: str

class MateriaStatsOut(Schema):
    materia_id: int
    materia_nombre: str
    materia_anio: int
    carreras_codigos: str
    dias_cursada: list[str]
    asistencias: int
    asincronicas: int
    faltas: int
    historial: list[HistorialClaseOut]
