#!/usr/bin/env bash
# install.sh - Installs Docker CLI tools for remote Docker daemon access
# This script runs during Docker image build (as root)

set -euo pipefail

DOCKER_VERSION=24.0.7
DOCKER_BUILDX_VERSION=0.12.1

echo "Installing Docker CLI v${DOCKER_VERSION}..."

# Install Docker CLI (client only, no daemon)
curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz" \
  -o /tmp/docker.tgz
tar xzf /tmp/docker.tgz -C /tmp/
install -m 755 /tmp/docker/docker /usr/bin/docker

echo "Installing Docker Buildx v${DOCKER_BUILDX_VERSION}..."

# Install Docker Buildx plugin
mkdir -p /usr/lib/docker/cli-plugins/
curl -fsSL "https://github.com/docker/buildx/releases/download/v${DOCKER_BUILDX_VERSION}/buildx-v${DOCKER_BUILDX_VERSION}.linux-amd64" \
  -o /usr/lib/docker/cli-plugins/docker-buildx
chmod +x /usr/lib/docker/cli-plugins/docker-buildx

# Clean up
rm -rf /tmp/docker*

echo "Docker CLI tools installed successfully"

# Note: Certificate handling is done in the Dockerfile, not here
# The CA certificates are properly configured via update-ca-certificates
# and NODE_EXTRA_CA_CERTS environment variable
