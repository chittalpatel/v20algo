#!/bin/bash

pkill gunicorn

sleep 2

source venv/bin/activate

nohup gunicorn --config gunicorn_config.py app:app > gunicorn.log 2>&1 &

echo "Website restarted."
