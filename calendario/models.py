# apps/calendario/models.py
from django.db import models
from core.models import AuditoriaModel

class EventoCalendario(AuditoriaModel):
    fecha = models.DateField()
    descripcion = models.CharField(max_length=200)
    
    # Creado_por ya lo hereda de AuditoriaModel, no hace falta agregarlo explícitamente