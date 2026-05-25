# apps/asistencia/models.py
from django.db import models
from core.models import AuditoriaModel
from core.constants import EstadoSolicitud, TipoClase

class SolicitudEmergencia(AuditoriaModel):
    docente = models.ForeignKey('usuarios.Docente', on_delete=models.CASCADE)
    slot_horario = models.ForeignKey('academico.SlotHorario', on_delete=models.SET_NULL, null=True, blank=True)
    fecha = models.DateField()
    nota_docente = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=EstadoSolicitud.choices, default=EstadoSolicitud.PENDIENTE)
    nota_secretaria = models.TextField(blank=True)
    revisado_por = models.ForeignKey('usuarios.Secretario', on_delete=models.SET_NULL, null=True, blank=True)
    revisado_en = models.DateTimeField(null=True, blank=True)

class RegistroAsistencia(AuditoriaModel):
    docente = models.ForeignKey('usuarios.Docente', on_delete=models.CASCADE)
    slot_horario = models.ForeignKey('academico.SlotHorario', on_delete=models.CASCADE)
    fecha = models.DateField()
    anio = models.SmallIntegerField()
    tipo_clase = models.CharField(max_length=30, choices=TipoClase.choices)
    
    hora_entrada = models.DateTimeField(null=True, blank=True)
    hora_salida = models.DateTimeField(null=True, blank=True)
    ubicacion_validada = models.BooleanField(null=True, blank=True)
    
    latitud_registrada = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud_registrada = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    ip_registrada = models.GenericIPAddressField(null=True, blank=True)
    
    solicitud_emergencia = models.ForeignKey(SolicitudEmergencia, on_delete=models.SET_NULL, null=True, blank=True)
    nota = models.TextField(blank=True)

    class Meta:
        unique_together = ('docente', 'slot_horario', 'fecha')