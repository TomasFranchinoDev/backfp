from ninja import Router
from django.shortcuts import get_object_or_404
from typing import List
from datetime import date

from core.security import secretario_auth

from .models import EventoCalendario
from .schemas import EventoCalendarioIn, EventoCalendarioOut
from academico.schemas import MensajeOut

router = Router(tags=["Calendario Académico"], auth=secretario_auth)

@router.get("/", response=List[EventoCalendarioOut])
def listar_eventos(request, year: int = None, month: int = None):
    """
    Lista los eventos del calendario. 
    Permite filtrar opcionalmente por año y mes.
    """
    query = EventoCalendario.objects.all().order_by('fecha')
    
    if year:
        query = query.filter(fecha__year=year)
    if month:
        query = query.filter(fecha__month=month)
        
    return query

@router.post("/", response={201: EventoCalendarioOut, 400: MensajeOut})
def crear_evento(request, payload: EventoCalendarioIn):
    """Crea un nuevo día bloqueado/feriado en el calendario."""
    if EventoCalendario.objects.filter(fecha=payload.fecha).exists():
        return 400, {"success": False, "mensaje": "Ya existe un evento para esta fecha."}
        
    evento = EventoCalendario.objects.create(
        creado_por=request.user,
        **payload.dict()
    )
    return 201, evento

@router.delete("/{evento_id}", response={200: MensajeOut})
def eliminar_evento(request, evento_id: int):
    """Elimina físicamente un evento del calendario (no usamos borrado lógico acá porque si se equivocan, el día vuelve a ser laborable normal)."""
    evento = get_object_or_404(EventoCalendario, id=evento_id)
    evento.delete()
    return 200, {"success": True, "mensaje": "Evento eliminado del calendario. El día vuelve a ser laborable."}