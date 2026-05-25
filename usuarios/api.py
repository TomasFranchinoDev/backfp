from ninja import Router
from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest
from core.security import secretario_auth
from usuarios.models import Secretario
from .schemas import LoginIn, UsuarioOut, MensajeOut
from .services import obtener_rol_usuario
from usuarios.models import Usuario, Docente
from usuarios.schemas import UsuarioRegistroIn, UsuarioUpdateIn, DocenteOut, SecretarioOut, CambioEstadoIn, DashboardStatsOut
from core.security import secretario_auth
from django.shortcuts import get_object_or_404
from typing import List

router = Router(tags=["Autenticación"])


def _ok(mensaje: str) -> dict:
    return {"success": True, "mensaje": mensaje}


def _err(mensaje: str) -> dict:
    return {"success": False, "mensaje": mensaje}

@router.post("/login", response={200: UsuarioOut, 401: MensajeOut})
def api_login(request: HttpRequest, payload: LoginIn):
    # authenticate() verifica la DB y devuelve el usuario si la pass es correcta
    user = authenticate(request, username=payload.username, password=payload.password)
    
    if user is not None:
        login(request, user) # Esto es lo que crea la cookie HttpOnly en el navegador
        rol = obtener_rol_usuario(user)
        return 200, {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "rol": rol
        }
    
    return 401, {"success": False, "mensaje": "Credenciales inválidas"}

@router.post("/logout", response={200: MensajeOut})
def api_logout(request: HttpRequest):
    logout(request) # Destruye la sesión en el servidor y borra la cookie
    return 200, {"success": True, "mensaje": "Sesión cerrada correctamente"}

@router.get("/me", response={200: UsuarioOut, 401: MensajeOut})
def api_me(request: HttpRequest):
    # Endpoint vital para cuando el usuario cierra y vuelve a abrir la PWA en el celular
    if request.user.is_authenticated:
        rol = obtener_rol_usuario(request.user)
        return 200, {
            "id": request.user.id,
            "username": request.user.username,
            "email": request.user.email,
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "rol": rol
        }
    return 401, {"success": False, "mensaje": "No hay sesión activa"}

# ==========================================
# CRUD: DOCENTES
# ==========================================

@router.get("/docentes", response=List[DocenteOut], auth=secretario_auth)
def listar_docentes(request, incluir_inactivos: bool = False):
    """
    Devuelve los docentes. 
    Por defecto (para combos y asignaciones) devuelve solo ACTIVOS.
    Si incluir_inactivos=True (para la tabla del CRUD general), devuelve TODOS.
    """
    queryset = Docente.objects.select_related('user')
    
    if not incluir_inactivos:
        queryset = queryset.filter(activo=True)
        
    return queryset.order_by('-activo', 'user__last_name')

@router.post("/docentes", response={201: DocenteOut, 400: MensajeOut}, auth=secretario_auth)
def crear_docente(request, payload: UsuarioRegistroIn):
    """Crea el usuario base (hasheando la password) y su perfil Docente."""
    if Usuario.objects.filter(username=payload.username).exists():
        return 400, {"success": False, "mensaje": "El nombre de usuario (legajo/DNI) ya está en uso."}
    
    # 1. Usamos create_user para que encripte la contraseña correctamente
    user = Usuario.objects.create_user(
        username=payload.username,
        email=payload.email,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name
    )
    
    # 2. Creamos el perfil de docente vinculado a ese usuario
    docente = Docente.objects.create(user=user, creado_por=request.user)
    
    return 201, docente

@router.put("/docentes/{docente_id}", response={200: MensajeOut, 400: MensajeOut, 404: MensajeOut}, auth=secretario_auth)
def actualizar_docente(request, docente_id: int, payload: UsuarioUpdateIn):
    # 1. Buscar el perfil docente y su usuario asociado
    docente = Docente.objects.select_related('user').filter(id=docente_id).first()
    if not docente:
        return 404, _err("Docente no encontrado")
    
    user = docente.user
    
    # 2. Validar que el nuevo DNI no esté en uso por OTRO usuario
    if payload.username != user.username:
        if Usuario.objects.filter(username=payload.username).exclude(id=user.id).exists():
            return 400, _err("El DNI/Usuario ingresado ya está registrado en el sistema")
        user.username = payload.username

    # 3. Actualizar los datos básicos
    user.first_name = payload.first_name
    user.last_name = payload.last_name
    user.email = payload.email
    
    # 4. Tratar la contraseña de forma segura si fue enviada
    if payload.password and payload.password.strip():
        user.set_password(payload.password)
        
    user.save()
    
    return 200, _ok("Datos del docente actualizados correctamente")

@router.patch("/docentes/{docente_id}/estado", response={200: MensajeOut, 404: MensajeOut}, auth=secretario_auth)
def cambiar_estado_docente(request, docente_id: int, payload: CambioEstadoIn):
    """
    Activa o desactiva a un docente (y su usuario asociado para bloquear/permitir login).
    """
    docente = Docente.objects.select_related('user').filter(id=docente_id).first()
    if not docente:
        return 404, _err("Docente no encontrado")
    
    # 1. Cambiamos el estado lógico del perfil docente
    docente.activo = payload.activo
    docente.modificado_por = request.user
    docente.save()
    
    # 2. Bloqueamos el login a nivel de Django Auth
    docente.user.is_active = payload.activo
    docente.user.save()
    
    accion = "activado" if payload.activo else "desactivado"
    return 200, _ok(f"Docente {accion} exitosamente.")


# ==========================================
# CRUD: SECRETARIOS
# ==========================================

@router.get("/secretarios", response=List[SecretarioOut], auth=secretario_auth)
def listar_secretarios(request, incluir_inactivos: bool = False):
    """
    Devuelve los secretarios/administradores del sistema.
    Por defecto devuelve solo los activos. Si incluir_inactivos=True, devuelve todos.
    """
    queryset = Secretario.objects.select_related('user')
    
    if not incluir_inactivos:
        queryset = queryset.filter(activo=True)
        
    return queryset.order_by('-activo', 'user__last_name')

@router.post("/secretarios", response={201: SecretarioOut, 400: MensajeOut}, auth=secretario_auth)
def crear_secretario(request, payload: UsuarioRegistroIn):
    """Crea un usuario administrador/secretario."""
    if Usuario.objects.filter(username=payload.username).exists():
        return 400, {"success": False, "mensaje": "El nombre de usuario ya está en uso."}
    
    user = Usuario.objects.create_user(
        username=payload.username,
        email=payload.email,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name
    )
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    
    secretario = Secretario.objects.create(user=user, creado_por=request.user)
    return 201, secretario

@router.put("/secretarios/{secretario_id}", response={200: MensajeOut, 400: MensajeOut, 404: MensajeOut}, auth=secretario_auth)
def actualizar_secretario(request, secretario_id: int, payload: UsuarioUpdateIn):
    secretario = Secretario.objects.select_related('user').filter(id=secretario_id).first()
    if not secretario:
        return 404, _err("Secretario no encontrado")
    
    user = secretario.user
    
    if payload.username != user.username:
        if Usuario.objects.filter(username=payload.username).exclude(id=user.id).exists():
            return 400, _err("El DNI/Usuario ingresado ya está registrado en el sistema")
        user.username = payload.username

    user.first_name = payload.first_name
    user.last_name = payload.last_name
    user.email = payload.email
    
    if payload.password and payload.password.strip():
        user.set_password(payload.password)
        
    user.save()
    
    return 200, _ok("Datos del secretario actualizados correctamente")

@router.patch("/secretarios/{secretario_id}/estado", response={200: MensajeOut, 404: MensajeOut}, auth=secretario_auth)
def cambiar_estado_secretario(request, secretario_id: int, payload: CambioEstadoIn):
    secretario = Secretario.objects.select_related('user').filter(id=secretario_id).first()
    if not secretario:
        return 404, _err("Secretario no encontrado")
    
    secretario.activo = payload.activo
    secretario.modificado_por = request.user
    secretario.save()
    
    secretario.user.is_active = payload.activo
    secretario.user.save()
    
    accion = "activado" if payload.activo else "desactivado"
    return 200, _ok(f"Secretario {accion} exitosamente.")


@router.get("/secretario/dashboard-stats", response=DashboardStatsOut, auth=secretario_auth)
def obtener_dashboard_stats(request):
    """
    Retorna métricas consolidadas en tiempo real y el listado de docentes actualmente en el aula.
    """
    from django.utils import timezone
    from asistencia.models import SolicitudEmergencia, RegistroAsistencia
    from academico.models import SlotHorario
    from core.constants import EstadoSolicitud

    docentes_activos = Docente.objects.filter(activo=True).count()
    emergencias_pendientes = SolicitudEmergencia.objects.filter(estado=EstadoSolicitud.PENDIENTE).count()
    
    hoy = timezone.localdate()
    dia_semana_actual = hoy.weekday()
    clases_hoy = SlotHorario.objects.filter(dia_semana=dia_semana_actual).count()
    
    asistencias_activas = RegistroAsistencia.objects.filter(
        fecha=hoy,
        hora_salida__isnull=True
    ).select_related('docente__user', 'slot_horario__materia')
    
    docentes_en_aula = []
    for reg in asistencias_activas:
        docentes_en_aula.append({
            "docente_id": reg.docente.id,
            "docente_nombre": reg.docente.user.get_full_name(),
            "materia_nombre": reg.slot_horario.materia.nombre,
            "hora_entrada": timezone.localtime(reg.hora_entrada).strftime("%H:%M") if reg.hora_entrada else "",
            "tipo_clase": reg.tipo_clase,
            "ubicacion_validada": reg.ubicacion_validada
        })
        
    return {
        "docentes_activos": docentes_activos,
        "emergencias_pendientes": emergencias_pendientes,
        "clases_hoy": clases_hoy,
        "docentes_en_aula": docentes_en_aula
    }


