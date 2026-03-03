"""WSGI entry point for gunicorn and Flask dev server.

Usage:
  # Development
  uv run flask --app wsgi:app run --debug

  # Production (gunicorn)
  uv run gunicorn --bind 0.0.0.0:5000 --workers 2 wsgi:app
"""

from trading_journal.web import create_app

app = create_app()
