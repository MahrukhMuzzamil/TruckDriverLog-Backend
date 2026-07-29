#!/bin/sh
set -e

# Apply migrations only from the web container (RUN_MIGRATIONS=1);
# celery workers just wait for the database to be ready.
if [ "$RUN_MIGRATIONS" = "1" ]; then
  echo "Applying database migrations..."
  python manage.py migrate --noinput
  echo "Collecting static files..."
  python manage.py collectstatic --noinput
fi

exec "$@"
