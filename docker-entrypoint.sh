#!/bin/bash
set -e
echo "Running database migrations..."
uv run python main.py db migrate
echo "Migrations complete. Starting server..."
exec "$@"
