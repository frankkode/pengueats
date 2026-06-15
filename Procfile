release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn pengueats.wsgi --bind 0.0.0.0:$PORT --log-file -
