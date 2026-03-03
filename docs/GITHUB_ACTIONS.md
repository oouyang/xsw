# GitHub Actions - Docker Image Build

This repository uses GitHub Actions to automatically build and push Docker images for both the backend (xsw) and frontend (web) services.

## Workflow Overview

**File**: `.github/workflows/build-docker-images.yml`

### Triggers

The workflow runs on:
- **Push to main/master**: Builds and pushes with `edge` + `latest` tags
- **Version tags** (e.g., `v1.0.0`): Builds and pushes with version + `latest` tags
- **Pull requests**: Builds only (no push)
- **Manual trigger**: Can be run manually from GitHub Actions tab

### Images Built

1. **Backend (xsw)**: `oouyang/xsw:latest`
2. **Frontend (web)**: `oouyang/xsw:latest-web`

## Setup Instructions

### 1. Create Docker Hub Access Token

1. Go to https://hub.docker.com/settings/security
2. Click **New Access Token**
3. Name: `github-actions-xsw`
4. Permissions: **Read, Write, Delete**
5. Click **Generate** and copy the token

### 2. Add GitHub Secrets

Go to your repository settings:
- Navigate to **Settings** → **Secrets and variables** → **Actions**
- Click **New repository secret**

Add these two secrets:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `DOCKERHUB_USERNAME` | `oouyang` | Your Docker Hub username |
| `DOCKERHUB_TOKEN` | `dckr_pat_...` | The access token from step 1 |

### 3. Verify Workflow

1. Make a small change and push to master:
   ```bash
   git add .
   git commit -m "test: trigger Docker build"
   git push origin master
   ```

2. Check the workflow:
   - Go to **Actions** tab in GitHub
   - Click on the running workflow
   - Verify both images are built and pushed

## Usage

### Automatic Builds

**Push to master/main:**
```bash
git push origin master
# → Builds oouyang/xsw:latest and oouyang/xsw:latest-web
```

**Create version tag:**
```bash
git tag v1.0.0
git push origin v1.0.0
# → Builds oouyang/xsw:1.0.0 and oouyang/xsw:1.0.0-web
# → Also updates 'latest' tags
```

### Manual Trigger

1. Go to **Actions** tab
2. Select **Build and Push Docker Images** workflow
3. Click **Run workflow**
4. Choose options:
   - Branch: `master`
   - Push images: `true` (or `false` to build only)
5. Click **Run workflow**

## Workflow Features

### Build Optimization

- **BuildKit**: Uses Docker Buildx for advanced caching
- **GitHub Actions Cache**: Caches layers between builds (faster rebuilds)
- **Multi-stage build**: Efficient layer reuse

### Tagging Strategy

| Event | Tags |
|-------|------|
| Push to master | `edge`, `latest` |
| Tag `v1.2.3` | `1.2.3`, `latest` |
| Pull request | Build only (no tags) |

### Build Args

The workflow passes these build arguments:

```dockerfile
BASE_URL=https://czbooks.net
AUTH_ENABLED=true
```

To customize, edit the workflow file and add/modify under `build-args:`.

## Deployment

After images are pushed to Docker Hub, deploy them:

### Docker Compose

```bash
# Pull latest images
docker compose pull

# Restart services
docker compose up -d
```

### Manual Pull

```bash
# Backend
docker pull oouyang/xsw:latest

# Frontend
docker pull oouyang/xsw:latest-web
```

## Troubleshooting

### Build Fails with "Authentication Required"

**Cause**: Missing or invalid Docker Hub credentials

**Fix**:
1. Verify secrets are set correctly in repository settings
2. Check that Docker Hub token hasn't expired
3. Ensure token has **Write** permissions

### Build Fails with "Permission Denied"

**Cause**: Workflow doesn't have write permissions

**Fix**: Check that workflow has proper permissions:
```yaml
permissions:
  contents: read
  packages: write
```

### Build Times Out

**Cause**: Dependencies taking too long to install

**Fix**:
1. Check that npm cache is working (`cache: npm`)
2. Verify pip cache is mounted correctly
3. Consider increasing timeout in workflow

### Images Not Showing in Docker Hub

**Cause**: Push is disabled for pull requests

**Fix**: Only pushes occur on:
- Push to main/master
- Version tags
- Manual trigger with "Push images" = true

Check workflow logs for "push: false" if images aren't appearing.

## Monitoring

### View Build Status

Badge for README:
```markdown
![Docker Build](https://github.com/YOUR_ORG/xsw/actions/workflows/build-docker-images.yml/badge.svg)
```

### Check Image Sizes

```bash
# View image details
docker images oouyang/xsw

# Check backend size
docker inspect oouyang/xsw:latest | jq '.[0].Size'

# Check frontend size
docker inspect oouyang/xsw:latest-web | jq '.[0].Size'
```

### View Build History

1. Go to **Actions** tab
2. Click on **Build and Push Docker Images**
3. See all workflow runs with status and duration

## Advanced Configuration

### Corporate Proxy (Micron)

If building behind a corporate proxy, add these build args:

```yaml
build-args: |
  BASE_URL=https://czbooks.net
  AUTH_ENABLED=true
  INDEX_URL=https://boartifactory.micron.com/artifactory/api/pypi/micron-pypi-rel-virtual/simple
  TRUSTED_HOST=boartifactory.micron.com
```

### Multi-Platform Builds

To build for multiple architectures (amd64, arm64):

```yaml
- name: Build and push backend
  uses: docker/build-push-action@v5
  with:
    platforms: linux/amd64,linux/arm64
    # ... rest of config
```

### Custom Registry

To push to a different registry (e.g., GHCR):

```yaml
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
```

Then update secrets to use `GITHUB_TOKEN` instead of Docker Hub credentials.

## Performance Tips

1. **Parallel builds**: Both images build in parallel automatically
2. **Layer caching**: GitHub Actions cache persists between runs
3. **Build cache**: Docker BuildKit cache reuses layers efficiently
4. **Skip tests**: To skip frontend tests, remove this line from Dockerfile:
   ```dockerfile
   RUN npx vitest run --reporter=verbose
   ```

## Security Best Practices

1. **Never commit Docker Hub tokens** - Always use GitHub Secrets
2. **Use access tokens, not passwords** - More secure and revocable
3. **Limit token scope** - Only give Read/Write permissions
4. **Rotate tokens regularly** - Regenerate tokens every 6-12 months
5. **Review workflow logs** - Check for exposed secrets (GitHub automatically redacts them)

## Cost Optimization

GitHub Actions free tier:
- **Public repos**: Unlimited minutes
- **Private repos**: 2,000 minutes/month

Docker Hub free tier:
- **Pulls**: Unlimited
- **Pushes**: Unlimited
- **Storage**: Unlimited public repos

Estimated workflow duration:
- **First build**: ~8-10 minutes (no cache)
- **Cached build**: ~3-5 minutes
- **Pull request build**: ~4-6 minutes (no push)

## Related Documentation

- [Docker Build](../docker/README.md)
- [Deployment Guide](../README.md#deployment)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Build Push Action](https://github.com/docker/build-push-action)
