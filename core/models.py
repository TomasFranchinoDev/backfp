# apps/core/models.py
from django.db import models
from django.conf import settings

class AuditoriaModel(models.Model):
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name="%(app_label)s_%(class)s_creado"
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name="%(app_label)s_%(class)s_modificado"
    )

    class Meta:
        abstract = True