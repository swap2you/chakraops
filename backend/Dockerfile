# Backend image. Build from repo root: docker build -f backend/Dockerfile .
# Canonical out/ path in container: /workspace/out (mount at run via compose).
FROM python:3.13-slim

WORKDIR /workspace

# Depth is unchanged: parents[4] from backend/app/core/operations is /workspace.
COPY backend /workspace/backend

WORKDIR /workspace/backend
ENV PYTHONPATH=/workspace/backend
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

# .env not copied; use env_file in docker-compose.
CMD ["python", "-m", "uvicorn", "app.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
