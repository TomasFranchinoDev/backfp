from ninja import Router
from django.shortcuts import get_object_or_404
from typing import List
from core.security import secretario_auth
from django.db import transaction
from django.utils import timezone

from .models import Carrera, Materia, SlotHorario
from asignaciones.models import AsignacionDocente
from .schemas import (
    CarreraIn, CarreraOut,
    MateriaIn, MateriaOut,
    SlotHorarioIn, SlotHorarioOut,
    MensajeOut,
)
from .services import materia_to_out, sincronizar_carreras_materia, obtener_materia_con_carreras

# El router completo requiere que el usuario tenga una sesión válida
router = Router(tags=["Catálogo Académico"], auth=secretario_auth)

# ==========================================
# CRUD: MATERIAS
# ==========================================
@router.get("/materias", response=List[MateriaOut])
def listar_materias(request, incluir_inactivas: bool = False):
    """
    Devuelve materias con sus carreras asociadas.
    Por defecto solo activas (combos). Con incluir_inactivas=True, devuelve todas.
    """
    queryset = Materia.objects.prefetch_related('carreras_asociadas__carrera').order_by('-activa', 'nombre')

    if not incluir_inactivas:
        queryset = queryset.filter(activa=True)

    return [materia_to_out(materia) for materia in queryset]

@router.post("/materias", response={201: MateriaOut, 400: MensajeOut})
def crear_materia(request, payload: MateriaIn):
    """Crea una nueva materia y sincroniza sus carreras."""
    if not payload.carreras_ids:
        return 400, {"success": False, "mensaje": "Debe asociar al menos una carrera."}

    if Materia.objects.filter(codigo_siu=payload.codigo_siu, anio=payload.anio).exists():
        return 400, {"success": False, "mensaje": "Ya existe esta materia para este año."}

    datos = payload.dict()
    carreras_ids = datos.pop('carreras_ids')

    materia = Materia.objects.create(**datos, creado_por=request.user)

    try:
        sincronizar_carreras_materia(materia, carreras_ids, request.user)
    except ValueError as exc:
        materia.delete()
        return 400, {"success": False, "mensaje": str(exc)}

    materia = obtener_materia_con_carreras(materia.id)
    return 201, materia_to_out(materia)

@router.put("/materias/{materia_id}", response={200: MateriaOut, 400: MensajeOut})
def actualizar_materia(request, materia_id: int, payload: MateriaIn):
    """Actualiza una materia existente y sincroniza sus carreras."""
    if not payload.carreras_ids:
        return 400, {"success": False, "mensaje": "Debe asociar al menos una carrera."}

    materia = get_object_or_404(Materia, id=materia_id)

    datos = payload.dict()
    carreras_ids = datos.pop('carreras_ids')

    for attr, value in datos.items():
        setattr(materia, attr, value)

    materia.modificado_por = request.user
    materia.save()

    try:
        sincronizar_carreras_materia(materia, carreras_ids, request.user)
    except ValueError as exc:
        return 400, {"success": False, "mensaje": str(exc)}

    materia = obtener_materia_con_carreras(materia.id)
    return 200, materia_to_out(materia)

@router.delete("/materias/{materia_id}", response={200: MensajeOut})
def borrar_materia(request, materia_id: int):
    """Borrado lógico de la materia."""
    materia = get_object_or_404(Materia, id=materia_id)
    AsignacionDocente.objects.filter(materia=materia, activa=True).update(
        activa=False,
        modificado_por=request.user,
    )
    materia.activa = False
    materia.modificado_por = request.user
    materia.save()
    return 200, {"success": True, "mensaje": "Materia desactivada correctamente"}

# ==========================================
# CRUD: SLOTS HORARIOS
# ==========================================
@router.get("/slots", response=List[SlotHorarioOut])
def listar_slots(request):
    """Lista todos los bloques horarios actuales del catálogo académico."""
    return SlotHorario.objects.filter(valido_hasta__isnull=True).select_related('materia').order_by(
        'materia__nombre', 'dia_semana', 'hora_inicio'
    )

@router.get("/materias/{materia_id}/slots", response=List[SlotHorarioOut])
def listar_slots_por_materia(request, materia_id: int):
    """Obtiene los horarios actuales asignados a una materia específica."""
    return SlotHorario.objects.filter(materia_id=materia_id, valido_hasta__isnull=True)

@router.post("/slots", response={201: SlotHorarioOut})
def crear_slot(request, payload: SlotHorarioIn):
    """Crea un bloque horario para una materia."""
    materia = get_object_or_404(Materia, id=payload.materia_id)
    datos = payload.dict(exclude={'materia_id'})
    slot = SlotHorario.objects.create(materia=materia, creado_por=request.user, **datos)
    return 201, slot

# ==========================================
# CRUD: SLOTS HORARIOS - UPDATE / DELETE
# ==========================================
@router.put("/slots/{slot_id}", response={200: SlotHorarioOut, 404: MensajeOut})
def actualizar_slot(request, slot_id: int, payload: SlotHorarioIn):
    """Actualiza un bloque horario existente (versionándolo)."""
    with transaction.atomic():
        slot_viejo = get_object_or_404(SlotHorario, id=slot_id)
        materia = get_object_or_404(Materia, id=payload.materia_id)
        
        hoy = timezone.localdate()
        
        # Cerramos el slot viejo
        slot_viejo.valido_hasta = hoy
        slot_viejo.modificado_por = request.user
        slot_viejo.save()
        
        # Creamos el slot nuevo con los datos actualizados
        datos = payload.dict(exclude={'materia_id'})
        slot_nuevo = SlotHorario.objects.create(
            materia=materia,
            valido_desde=hoy + timezone.timedelta(days=1),
            creado_por=request.user,
            **datos
        )
    return 200, slot_nuevo

@router.delete("/slots/{slot_id}", response={200: MensajeOut})
def borrar_slot(request, slot_id: int):
    """Elimina lógicamente un bloque horario."""
    slot = get_object_or_404(SlotHorario, id=slot_id)
    slot.valido_hasta = timezone.localdate()
    slot.modificado_por = request.user
    slot.save()
    return 200, {"success": True, "mensaje": "Slot eliminado correctamente"}


# ==========================================
# CRUD: CARRERAS
# ==========================================
@router.get("/carreras", response=List[CarreraOut])
def listar_carreras(request):
    """Devuelve todas las carreras."""
    return Carrera.objects.all()

@router.post("/carreras", response={201: CarreraOut, 400: MensajeOut})
def crear_carrera(request, payload: CarreraIn):
    """Crea una nueva carrera."""
    if Carrera.objects.filter(codigo=payload.codigo).exists():
        return 400, {"success": False, "mensaje": "Ya existe una carrera con ese código."}
    carrera = Carrera.objects.create(**payload.dict(), creado_por=request.user)
    return 201, carrera

@router.put("/carreras/{carrera_id}", response={200: CarreraOut})
def actualizar_carrera(request, carrera_id: int, payload: CarreraIn):
    """Actualiza una carrera existente."""
    carrera = get_object_or_404(Carrera, id=carrera_id)
    for attr, value in payload.dict().items():
        setattr(carrera, attr, value)
    carrera.modificado_por = request.user
    carrera.save()
    return 200, carrera

@router.delete("/carreras/{carrera_id}", response={200: MensajeOut})
def borrar_carrera(request, carrera_id: int):
    """Elimina una carrera."""
    carrera = get_object_or_404(Carrera, id=carrera_id)
    carrera.delete()
    return 200, {"success": True, "mensaje": "Carrera eliminada correctamente"}


# ==========================================
# CRUD: SLOTS POR CARRERA
# ==========================================
@router.get("/carreras/{carrera_id}/slots", response=List[SlotHorarioOut])
def listar_slots_por_carrera(request, carrera_id: int):
    """Lista los slots horarios actuales asociados a las materias de una carrera."""
    return SlotHorario.objects.filter(materia__carreras_asociadas__carrera_id=carrera_id, valido_hasta__isnull=True).distinct()