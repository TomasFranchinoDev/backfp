from ninja import Schema
from typing import Optional
from pydantic import EmailStr

class LoginIn(Schema):
    username: str
    password: str

class CambioEstadoIn(Schema):
    activo: bool

class UsuarioOut(Schema):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    rol: str  # Retornaremos 'docente', 'secretario' o 'admin'

class MensajeOut(Schema):
    success: bool
    mensaje: str

class UsuarioRegistroIn(Schema):
    username: str
    email: EmailStr
    password: str
    first_name: str
    last_name: str

class UsuarioUpdateIn(Schema):
    username: str  # El DNI (obligatorio por si se corrige)
    first_name: str
    last_name: str
    email: EmailStr
    password: Optional[str] = None  # Opcional: si viene, se cambia; si no, queda igual.

class PerfilUsuarioOut(Schema):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str

# --- Esquemas de Salida (Docente y Secretario) ---

class DocenteOut(Schema):
    id: int
    user: PerfilUsuarioOut  # Anidamos los datos del usuario base
    activo: bool

class SecretarioOut(Schema):
    id: int
    user: PerfilUsuarioOut
    activo: bool

# --- Esquemas para el Dashboard ---

class DocenteEnAulaOut(Schema):
    docente_id: int
    docente_nombre: str
    materia_nombre: str
    hora_entrada: str
    tipo_clase: str
    ubicacion_validada: Optional[bool] = None

class DashboardStatsOut(Schema):
    docentes_activos: int
    emergencias_pendientes: int
    clases_hoy: int
    docentes_en_aula: list[DocenteEnAulaOut]
