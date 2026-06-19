# apps/core/constants.py
from django.db import models

class Institucion(models.TextChoices):
    ICES = 'ices', 'ICES'
    UCSE = 'ucse', 'UCSE'

class DiaSemana(models.IntegerChoices):
    # Usamos enteros (0=Lunes, 6=Domingo) para alinear con el estándar datetime de Python
    LUNES = 0, 'Lunes'
    MARTES = 1, 'Martes'
    MIERCOLES = 2, 'Miércoles'
    JUEVES = 3, 'Jueves'
    VIERNES = 4, 'Viernes'
    SABADO = 5, 'Sábado'
    DOMINGO = 6, 'Domingo'

class RolDocente(models.TextChoices):
    TITULAR = 'titular', 'Titular'
    ADJUNTO = 'adjunto', 'Adjunto'

class TipoClase(models.TextChoices):
    PRESENCIAL = 'presencial', 'Presencial'
    VIRTUAL_SINCRONICA = 'virtual_sincronica', 'Virtual Sincrónica'
    ASINCRONICA = 'asincronica', 'Asincrónica'

class EstadoSolicitud(models.TextChoices):
    PENDIENTE = 'pendiente', 'Pendiente'
    APROBADA = 'aprobada', 'Aprobada'
    RECHAZADA = 'rechazada', 'Rechazada'

class MetodoValidacion(models.TextChoices):
    GPS_O_WIFI = 'gps_o_wifi', 'GPS o WiFi'
    SOLO_WIFI = 'solo_wifi', 'Solo WiFi'
    SOLO_GPS = 'solo_gps', 'Solo GPS'