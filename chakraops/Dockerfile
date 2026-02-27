# R24.8: Backend Docker packaging. Build from repo root: docker build -f chakraops/Dockerfile .
# Canonical out/ path in container: /workspace/out (mount at run via compose).
FROM python:3.12-slim

WORKDIR /workspace

# Copy only chakraops so that Path(__file__).parents[4] = /workspace (repo root in container).
COPY chakraops /workspace/chakraops

WORKDIR /workspace/chakraops
ENV PYTHONPATH=/workspace/chakraops
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

# .env not copied; use env_file in docker-compose.
CMD ["python", "-m", "uvicorn", "app.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
