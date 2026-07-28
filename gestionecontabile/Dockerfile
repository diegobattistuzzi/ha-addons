FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend
COPY --from=frontend-builder /build/frontend/dist ./backend/public

ENV PORT=8099
ENV DATA_DIR=/data

EXPOSE 8099
CMD ["uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8099"]
