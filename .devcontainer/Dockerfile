# syntax=docker/dockerfile:1.7
# Full-stack devcontainer: Node.js 20 + Python 3.11 for XSW project
FROM mcr.microsoft.com/devcontainers/python:3.11

# ---- Build args for proxy (so build steps can download via proxy) ----
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

# ---- System deps & CA installation ----
USER root

# Create a dedicated folder for corporate CA
RUN set -eux; \
    mkdir -p /usr/local/share/ca-certificates/micron

# Fetch and install Micron CA certificates
# Note: If you want to bake certificates into the image for air-gapped builds,
# copy them from the build context instead:
# COPY certificates/*.crt /usr/local/share/ca-certificates/micron/
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl openssl; \
    curl -fsSL http://pki.micron.com/pki/Micron%20Technology%20Root%20CA.crt \
      | openssl x509 -out /usr/local/share/ca-certificates/micron/Micron_Root_CA.crt; \
    curl -fsSL http://pki.micron.com/pki/Micron%20Technology%20Issuing%20CA.crt \
      | openssl x509 -out /usr/local/share/ca-certificates/micron/Micron_Issuing_CA.crt; \
    update-ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Create a CA bundle file that combines both certificates
# This is needed for NODE_EXTRA_CA_CERTS to work properly
RUN set -eux; \
    cat /usr/local/share/ca-certificates/micron/Micron_Root_CA.crt \
        /usr/local/share/ca-certificates/micron/Micron_Issuing_CA.crt \
        > /usr/local/share/ca-certificates/micron/ca-bundle.crt

# ---- Install Node.js via NodeSource (LTS version 20) ----
RUN set -eux; \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -; \
    apt-get install -y nodejs; \
    node --version; \
    npm --version

# ---- Common CLI quality-of-life tools ----
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      vim \
      bash-completion \
      git \
      unzip \
      jq \
      locales \
      apt-transport-https \
      gnupg \
      wget \
      # SQLite tools for database inspection
      sqlite3 \
      # Python build dependencies
      build-essential \
      python3-dev; \
    rm -rf /var/lib/apt/lists/*

# ---- Node toolchain setup ----
# Enable Corepack (bundled with Node 18+) for pnpm/yarn management
RUN corepack enable || true

# ---- Project-provided provisioning scripts (optional) ----
# Copy and execute any custom setup scripts from library-scripts/
COPY .devcontainer/library-scripts/*.sh /tmp/library-scripts/
RUN set -eux; \
    if [ -d /tmp/library-scripts ]; then \
      chmod +x /tmp/library-scripts/*.sh; \
      for script in /tmp/library-scripts/*.sh; do \
        if [ -f "$script" ] && [ "$script" != "/tmp/library-scripts/postCreate.sh" ]; then \
          echo "Running $script..."; \
          bash "$script"; \
        fi; \
      done; \
      rm -rf /tmp/library-scripts; \
    fi

# ---- Locale configuration ----
RUN sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/g' /etc/locale.gen && \
    locale-gen

ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# ---- Drop to the non-root 'vscode' user (Python base image uses 'vscode', not 'node') ----
USER vscode
WORKDIR /workspaces

# Environment variables for SSL/TLS in corporate environments
ENV NODE_OPTIONS="--use-openssl-ca"
ENV NODE_EXTRA_CA_CERTS="/usr/local/share/ca-certificates/micron/ca-bundle.crt"
ENV REQUESTS_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt"

# Python environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Pre-create cache folders so Docker volumes can mount cleanly
RUN mkdir -p \
    /home/vscode/.cache \
    /home/vscode/.npm \
    /home/vscode/.yarn \
    /home/vscode/.local \
    /home/vscode/.cache/pip \
    /home/vscode/.cache/ruff

# Helpful message for developers
RUN echo "✅ DevContainer ready for XSW full-stack development (Python + Node.js)"
