#!/bin/sh
cd $WORKDIR
python manage.py collectstatic --noinput

gunicorn connect.wsgi --timeout 60 -c gunicorn.conf.py
