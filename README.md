# 🏫 Sistema de Control de Asistencia ICES - Backend

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-092E20.svg?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Django Ninja](https://img.shields.io/badge/Django_Ninja-1.6.2-1C2C39.svg?logo=fastapi&logoColor=white)](https://django-ninja.rest-framework.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

Un sistema integral y moderno de **fichaje docente y gestión de asistencia** diseñado para la institución ICES. Este repositorio contiene el **backend** de la aplicación, desarrollado con Python, Django y Django Ninja, que proporciona una API REST rápida, segura y altamente escalable para el frontend (SPA).

---

## 📸 Demostración
> *Nota para el reclutador: Aquí puedes colocar un GIF o captura de pantalla de la plataforma en funcionamiento (Swagger UI o el Frontend principal).*
<!-- ![Demo](ruta_a_la_imagen_o_gif.gif) -->

---

## 🎯 Objetivo Principal

El proyecto resuelve la necesidad de digitalizar y automatizar el registro de asistencia de los profesores. Permite administrar la estructura académica (carreras, años, materias), gestionar los horarios y asignaciones docentes, registrar fichajes diarios, y emitir reportes precisos para la administración.

---

## ✨ Características Principales

*   **Autenticación y Seguridad:** Sistema de login seguro usando Session Cookies HTTPOnly y protección CSRF integrada con el frontend.
*   **Gestión Académica:** ABM completo de Carreras, Materias, Profesores y Asignaciones.
*   **Fichaje Docente:** Registro de entradas y salidas en tiempo real mediante puntos finales de asistencia.
*   **Calendario Inteligente:** Manejo de horarios, días no laborables y feriados.
*   **Importación de Datos:** Capacidad para importar información masiva utilizando Pandas.
*   **Reportes Generados:** Extracción de reportes consolidados de asistencia.
*   **Documentación Interactiva:** API completamente documentada de forma automática (Swagger/OpenAPI).
*   **Servicio de Frontend:** Configuración con WhiteNoise para servir la SPA (Single Page Application) directamente desde Django.

---

## 💻 Tecnologías Utilizadas

*   **Lenguaje:** Python
*   **Framework principal:** Django 6.0
*   **API Framework:** Django Ninja (para endpoints rápidos y tipados estilo FastAPI)
*   **Base de Datos:** PostgreSQL (alojada en Supabase)
*   **Procesamiento de Datos:** Pandas & NumPy (para importación/exportación de excel)
*   **Despliegue y Servidor:** Gunicorn, WhiteNoise (para archivos estáticos)
*   **Seguridad y CORS:** django-cors-headers, python-dotenv

---

## 🚀 Lo que aprendí (Mi Rol)

En este proyecto actué como el **Desarrollador Backend Principal**, encargándome desde el diseño de la arquitectura hasta la puesta en producción.

**🏆 Principales retos técnicos superados:**
*   **Desarrollo de API Moderna:** Aprendí a implementar **Django Ninja**, aprovechando las ventajas de Pydantic y el tipado estático en Python para crear endpoints mucho más rápidos de desarrollar y documentar que con Django REST Framework.
*   **Seguridad SPA Desacoplada:** Logré configurar con éxito el manejo de sesiones (Session Cookies seguras) y tokens CSRF entre un frontend de React y el backend de Django, superando los desafíos comunes de CORS (`CORS_ALLOW_CREDENTIALS`) y SameSite cookies.
*   **Integración de Producción y Supabase:** Configuré el proyecto para conectarse eficientemente a una base de datos PostgreSQL alojada en **Supabase**, utilizando pools de conexión (`CONN_MAX_AGE`) para mejorar el rendimiento en producción.
*   **Despliegue Híbrido:** Implementé una arquitectura donde Django no solo sirve la API bajo `/api/`, sino que también actúa como servidor de archivos estáticos capturando el resto del tráfico (`re_path`) para servir la compilación de la SPA (`dist/`) usando WhiteNoise.

---

## ⚙️ Instalación y Uso (Modo Desarrollo)

Si deseas probar este proyecto en tu entorno local, sigue estos pasos:

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/TomasFranchinoDev/backfp.git
   cd backfp
   ```

2. **Crear y activar un entorno virtual**
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar las variables de entorno**
   Crea un archivo `.env` en la raíz del proyecto y agrega las variables necesarias basándote en la configuración de `config/settings.py` (ej: `SECRET_KEY`, `DEBUG`, credenciales de DB, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`).

5. **Aplicar migraciones**
   ```bash
   python manage.py migrate
   ```

6. **Crear un superusuario (opcional)**
   ```bash
   python manage.py createsuperuser
   ```

7. **Ejecutar el servidor local**
   ```bash
   python manage.py runserver
   ```

8. **Explorar la API**
   Abre tu navegador y ve a `http://127.0.0.1:8000/api/docs` para ver la documentación interactiva de Swagger UI.

---
*Desarrollado por [Tomás Franchino](https://github.com/TomasFranchinoDev)*
