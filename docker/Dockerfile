FROM node:22-alpine AS builder

WORKDIR /app
COPY package*.json ./web/
RUN npm config set strict-ssl false && npm i -g @quasar/cli && npm ci --prefix ./web --ignore-scripts
COPY . ./web
# Run quasar prepare only if project config exists
RUN if [ -f ./web/quasar.config.js ] || [ -f ./web/quasar.conf.js ]; then \
      npx --prefix ./web quasar prepare; \
    else \
      echo "Skipping quasar prepare: config not found"; \
    fi 
RUN npm --prefix ./web run build

FROM python:3.11-slim AS app

# 1) Declare build-time args (can have optional defaults)
ARG INDEX_URL
ARG TRUSTED_HOST

# 2) Promote them to runtime env vars (no further expansion)
ENV INDEX_URL=$INDEX_URL
ENV TRUSTED_HOST=$TRUSTED_HOST

WORKDIR /app
RUN  if [ -n "${INDEX_URL}" ] && [ -n "${TRUSTED_HOST}" ]; then \
      pip config set global.index-url "${INDEX_URL}" && \
      pip config set global.trusted-host "${TRUSTED_HOST}"; \
    else \
      echo "Skipping pip config because INDEX_URL or TRUSTED_HOST is not set"; \
    fi && \
    pip install --no-cache-dir fastapi uvicorn bs4 requests lxml ruff && \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      curl jq && \
    rm -rf /var/lib/apt/lists/*

COPY . .
COPY --from=builder /app/web/dist/spa/* /app/dist/spa
ENV BASE_URL=localhost
RUN ruff check && ruff format && echo $BASE_URL

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
