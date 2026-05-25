from ninja import Router
from django.shortcuts import get_object_or_404
from typing import List
from core.security import secretario_auth
from .models import AsignacionDocente
from .schemas import AsignacionDocenteIn, AsignacionDocenteOut
from usuarios.models import Docente
from academico.models import Materia
from academico.schemas import MensajeOut

router = Router(tags=["Asignaciones Docentes"], auth=secretario_auth)

@router.get("/", response=List[AsignacionDocenteOut])
def listar_asignaciones(request, docente_id: int = None):
    """Lista asignaciones. Permite filtrar por docente_id opcionalmente."""
    query = AsignacionDocente.objects.filter(activa=True)
    if docente_id:
        query = query.filter(docente_id=docente_id)
    return query

@router.post("/", response={201: AsignacionDocenteOut, 400: MensajeOut})
def crear_asignacion(request, payload: AsignacionDocenteIn):
    """Asigna un docente a una materia."""
    # Validar que docente y materia existan (el get_object_or_404 lanza error si no)
    docente = get_object_or_404(Docente, id=payload.docente)
    materia = get_object_or_404(Materia, id=payload.materia)
    
    # Extraemos los datos omitiendo los IDs relacionales para pasarlos como objetos
    datos = payload.dict(exclude={'docente', 'materia'})
    
    asignacion = AsignacionDocente.objects.create(
        docente=docente,
        materia=materia,
        creado_por=request.user,
        **datos
    )
    return 201, asignacion

@router.put("/{asignacion_id}", response={200: AsignacionDocenteOut, 400: MensajeOut})
def actualizar_asignacion(request, asignacion_id: int, payload: AsignacionDocenteIn):
    """Actualiza una asignación existente."""
    asignacion = get_object_or_404(AsignacionDocente, id=asignacion_id)
    docente = get_object_or_404(Docente, id=payload.docente)
    materia = get_object_or_404(Materia, id=payload.materia)
    
    asignacion.docente = docente
    asignacion.materia = materia
    asignacion.rol = payload.rol
    asignacion.fecha_inicio = payload.fecha_inicio
    asignacion.fecha_fin = payload.fecha_fin
    asignacion.modificado_por = request.user
    asignacion.save()
    
    return 200, asignacion

@router.delete("/{asignacion_id}", response={200: MensajeOut})
def desactivar_asignacion(request, asignacion_id: int):
    """Borrado lógico de la asignación."""
    asignacion = get_object_or_404(AsignacionDocente, id=asignacion_id)
    asignacion.activa = False
    asignacion.modificado_por = request.user
    asignacion.save()
    return 200, {"success": True, "mensaje": "Asignación desactivada"}