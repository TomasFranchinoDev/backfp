# apps/usuarios/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from core.models import AuditoriaModel

# Creamos nuestro propio usuario, pero hereda TODA la lógica de Django
class Usuario(AbstractUser):
    # Por ahora no agregamos nada extra, nos quedamos con username, email, password, etc.
    pass

class Docente(AuditoriaModel):
    # Apuntamos al nuevo modelo de usuario usando la configuración
    user = models.OneToOneField('usuarios.Usuario', on_delete=models.CASCADE)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.user.get_full_name()

class Secretario(AuditoriaModel):
    user = models.OneToOneField('usuarios.Usuario', on_delete=models.CASCADE)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.user.get_full_name()
