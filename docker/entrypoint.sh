#!/bin/bash
set -e

echo "=== Event Photography & AI Face Recognition System Startup ==="

# Wait for PostgreSQL database to accept connections
if [ -n "$DATABASE_URL" ]; then
    echo "Testing cloud database connection via DATABASE_URL..."
    python3 -c "
import sys, time
from app.config import settings
from sqlalchemy import create_engine, text

for i in range(30):
    try:
        engine = create_engine(settings.get_sync_database_url(), connect_args={'connect_timeout': 5})
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        print('Cloud PostgreSQL database connection ready.')
        sys.exit(0)
    except Exception as e:
        print(f'Waiting for cloud database... ({e})')
        time.sleep(1)
sys.exit(1)
"
elif [ -n "$POSTGRES_SERVER" ]; then
    echo "Waiting for database at $POSTGRES_SERVER:${POSTGRES_PORT:-5432}..."
    while ! nc -z "$POSTGRES_SERVER" "${POSTGRES_PORT:-5432}"; do
        sleep 1
    done
    echo "Database connection ready."
fi

# Ensure YuNet and SFace models are present and verified
if [ ! -f "models_zoo/face_detection_yunet_2023mar.onnx" ] || [ ! -f "models_zoo/face_recognition_sface_2021dec.onnx" ]; then
    echo "Downloading AI models from OpenCV Zoo..."
    python3 scripts/download_models.py
else
    echo "Pretrained ONNX face models verified."
fi

# Run database migrations
if [ "$RUN_MIGRATIONS" = "true" ] || [ "$1" = "uvicorn" ]; then
    echo "Applying Alembic database migrations..."
    alembic upgrade head
fi

echo "Executing command: $@"
exec "$@"

