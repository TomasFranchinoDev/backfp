# configuracion/models.py
from django.db import models
from core.models import AuditoriaModel
from core.constants import MetodoValidacion

class Configuracion(AuditoriaModel):
    # Forzamos que siempre sea ID=1 mediante la lógica en save() o en los servicios
    dia_corte_mensual = models.SmallIntegerField(default=20)
    red_wifi_campus = models.CharField(max_length=100, blank=True)
    metodo_validacion_ubicacion = models.CharField(
        max_length=30,
        choices=MetodoValidacion.choices,
        default=MetodoValidacion.GPS_O_WIFI,
    )
    latitud_campus = models.DecimalField(max_digits=9, decimal_places=6, default=-30.944598)
    longitud_campus = models.DecimalField(max_digits=9, decimal_places=6, default=-61.558501)
    radio_gps_metros = models.PositiveSmallIntegerField(default=150)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
