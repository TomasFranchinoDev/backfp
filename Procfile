web: gunicorn config.wsgi:application --log-file - --workers ${WEB_CONCURRENCY:-2} --bind 0.0.0.0:$PORT
release: python manage.py migrate --noinput