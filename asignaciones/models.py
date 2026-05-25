# apps/asignaciones/models.py
from django.db import models
from core.models import AuditoriaModel
from core.constants import RolDocente

class AsignacionDocente(AuditoriaModel):
    docente = models.ForeignKey('usuarios.Docente', on_delete=models.CASCADE, related_name='asignaciones')
    materia = models.ForeignKey('academico.Materia', on_delete=models.CASCADE, related_name='docentes_asignados')
    rol = models.CharField(max_length=20, choices=RolDocente.choices)
    activa = models.BooleanField(default=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
