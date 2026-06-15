#!/usr/bin/env bash
# One-shot setup + run script for PenguEats.
set -e
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data
echo "Starting PenguEats at http://127.0.0.1:8000  (Ctrl+C to stop)"
python manage.py runserver
