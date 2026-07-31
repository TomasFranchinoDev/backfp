# Usa Python 3.12-slim para que la imagen sea más ligera
FROM python:3.12-slim

# Evitar que Python escriba archivos .pyc en el disco y use buffer para la salida
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instalar dependencias del sistema necesarias para compilar psycopg2
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Copiar el archivo de dependencias
COPY requirements.txt /app/

# Instalar dependencias del proyecto
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiar el código del proyecto al contenedor
COPY . /app/

# Recolectar archivos estáticos para WhiteNoise durante el build
RUN python manage.py collectstatic --noinput

# Exponer el puerto interno
EXPOSE 8000

# Iniciar la aplicación usando Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]