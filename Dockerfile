# Stage 1: build the React frontend
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system --no-cache .

COPY backend/ backend/

# Copy built frontend into the Python package's static/ dir
COPY --from=frontend-build /frontend/dist backend/vouch/static/

ENV PYTHONPATH=/app/backend
ENV API_HOST=0.0.0.0
ENV API_PORT=8080

EXPOSE 8080

CMD ["uvicorn", "vouch.main:app", "--host", "0.0.0.0", "--port", "8080"]
