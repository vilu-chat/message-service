#!/bin/sh
set -e
# Migrations run here only when RUN_MIGRATIONS=true (set in docker-compose for local development).
# Never set it in Kubernetes: there, run `flask --app app db upgrade` once as a Job or init
# container before the new version starts, so replicas do not race each other.
if [ "$RUN_MIGRATIONS" = "true" ]; then
    flask --app app db upgrade
fi
exec gunicorn 'app:create_app()' --bind 0.0.0.0:8002 --workers 2 --threads 4
