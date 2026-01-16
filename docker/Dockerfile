FROM node:22-alpine AS builder

WORKDIR /web
COPY package*.json .
RUN --mount=type=cache,target=/root/.npm npm ci --ignore-scripts
COPY . .
# Run quasar prepare only if project config exists
RUN --mount=type=cache,target=/root/.npm npm run build && cd dist/spa && tar cvfz ../spa.tgz .

FROM python:3-alpine AS app

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
    pip install --no-cache-dir fastapi uvicorn bs4 requests lxml ruff 
    # && \
    # apt-get update && \
    # DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    #   curl jq && \
    # rm -rf /var/lib/apt/lists/*

COPY . .
COPY --from=builder /web/dist /app/dist
ENV BASE_URL=localhost
RUN ruff check && ruff format && echo $BASE_URL

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
