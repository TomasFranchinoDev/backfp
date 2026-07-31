from django.contrib.auth import get_user_model
from usuarios.models import Secretario

User = get_user_model()

# 1. Crear el usuario
nuevo_usuario = User.objects.create_user(
    username='secretario_admin',
    email='juan.perez@example.com',
    password='1234',
    first_name='Juan',
    last_name='Pérez',
    is_staff=True,
    is_active=True
)

# 2. Crear el perfil de Secretario vinculado a este usuario
Secretario.objects.create(user=nuevo_usuario)

print("¡Secretario creado y vinculado con éxito!")
