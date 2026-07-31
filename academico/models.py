# apps/academico/models.py
from django.db import models
from core.models import AuditoriaModel
from core.constants import Institucion, DiaSemana

class Carrera(AuditoriaModel):
    institucion = models.CharField(max_length=20, choices=Institucion.choices, default=Institucion.ICES)
    codigo = models.CharField(max_length=10, unique=True)
    nombre = models.CharField(max_length=200)
    duracion_anios = models.SmallIntegerField()

    def __str__(self):
        return f"[{self.codigo}] {self.nombre}"

class Materia(AuditoriaModel):
    codigo_siu = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=200)
    anio = models.SmallIntegerField()
    activa = models.BooleanField(default=True)

    class Meta:
        unique_together = ('codigo_siu', 'anio')

    def __str__(self):
        return f"{self.codigo_siu} - {self.nombre} ({self.anio})"

class MateriaCarrera(AuditoriaModel):
    materia = models.ForeignKey(Materia, on_delete=models.CASCADE, related_name='carreras_asociadas')
    carrera = models.ForeignKey(Carrera, on_delete=models.CASCADE, related_name='materias_asociadas')
    anio_plan = models.SmallIntegerField()

    class Meta:
        unique_together = ('materia', 'carrera')

from django.utils import timezone

class SlotHorario(AuditoriaModel):
    materia = models.ForeignKey(Materia, on_delete=models.CASCADE, related_name='slots')
    dia_semana = models.IntegerField(choices=DiaSemana.choices)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    valido_desde = models.DateTimeField(default=timezone.now)
    valido_hasta = models.DateTimeField(null=True, blank=True)

    def is_valid_at(self, target_date):
        """
        Calcula si este slot es válido en la fecha indicada, al momento exacto
        en que la clase debería iniciar.
        """
        import datetime
        from django.utils import timezone
        
        dt_start_naive = datetime.datetime.combine(target_date, self.hora_inicio)
        dt_start = timezone.make_aware(dt_start_naive)
        
        if self.valido_desde > dt_start:
            return False
        if self.valido_hasta and self.valido_hasta <= dt_start:
            return False
        return True