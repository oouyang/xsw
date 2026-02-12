# ============================================================
# Stage 1: Build the Vue/Quasar SPA (shared by both services)
# ============================================================
FROM node:22-alpine AS spa-builder
WORKDIR /web
COPY package*.json .
RUN --mount=type=cache,target=/root/.npm npm config set strict-ssl false && npm ci --ignore-scripts
COPY . .
RUN --mount=type=cache,target=/root/.npm npm run build

# ============================================================
# Stage 2: Nginx frontend (target: web)
# ============================================================
FROM nginx:1.16-alpine AS web
COPY --from=spa-builder /web/dist/spa /usr/share/nginx/html
COPY docker/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

# ============================================================
# Stage 3: Python backend (target: xsw)
# ============================================================
FROM python:3-alpine AS xsw

ARG INDEX_URL
ARG TRUSTED_HOST
ENV INDEX_URL=$INDEX_URL
ENV TRUSTED_HOST=$TRUSTED_HOST

WORKDIR /app

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -n "${INDEX_URL}" ] && [ -n "${TRUSTED_HOST}" ]; then \
      pip config set global.index-url "${INDEX_URL}" && \
      pip config set global.trusted-host "${TRUSTED_HOST}"; \
    else \
      echo "Skipping pip config because INDEX_URL or TRUSTED_HOST is not set"; \
    fi && \
    pip install -r requirements.txt && \
    pip install ruff && npm run test -- --reporter=verbose && pytest -v

COPY . .
COPY --from=spa-builder /web/dist /app/dist

ARG BASE_URL
ARG AUTH_ENABLED
ENV BASE_URL=$BASE_URL
ENV AUTH_ENABLED=$AUTH_ENABLED
ENV DB_PATH=/app/data/xsw_cache.db

RUN mkdir -p /app/data /app/dist/ubike && \
    ruff check && ruff format && echo $BASE_URL && \
    pip config unset global.index-url

EXPOSE 8000
CMD ["uvicorn", "main_optimized:app", "--host", "0.0.0.0", "--port", "8000"]
