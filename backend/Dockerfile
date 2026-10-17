# Build context is the repo root (see docker-compose.yml / render.yaml) so the
# image can include scripts/init_db.sql and seed/ for automatic DB bootstrap.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/backend

# Headless Chromium for the set-guide importer (reads checklist / odds pages). Its own layer,
# before requirements.txt, so adding a Python package doesn't download the browser again.
RUN pip install --no-cache-dir playwright==1.56.0 && python -m playwright install --with-deps chromium

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY scripts /srv/scripts
COPY seed /srv/seed

EXPOSE 8000
# $PORT is provided by Render/Railway/Fly; defaults to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
