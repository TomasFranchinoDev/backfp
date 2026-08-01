from django.db import models

class ImportTask(models.Model):
    task_id = models.CharField(max_length=100, unique=True, primary_key=True)
    estado = models.CharField(max_length=50, default="iniciado")
    fase = models.CharField(max_length=50, blank=True)
    paso = models.CharField(max_length=255, blank=True)
    progreso = models.IntegerField(default=0)
    resultado = models.JSONField(null=True, blank=True)
    errores = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Tarea {self.task_id} - {self.estado}"
