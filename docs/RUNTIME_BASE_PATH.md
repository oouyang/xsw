# Runtime Base Path Configuration

This document explains how the frontend automatically detects and adapts to different deployment paths at runtime.

## Overview

The Vue frontend can now be served from different base paths without rebuilding:

- **`/` (root)** - Standalone deployment (nginx, dev server)
- **`/spa/`** - FastAPI backend deployment
- **Custom path** - Any other base path

The base path is **automatically detected at runtime** from the URL, eliminating the need for separate builds.

## How It Works

### 1. Auto-Detection

When the app loads, it detects the base path from `window.location.pathname`:

```typescript
// If URL is: http://localhost:8000/spa/books/123
// Detected base path: /spa/

// If URL is: http://localhost:3000/books/123
// Detected base path: /
```

Detection logic ([src/utils/basePath.ts](../src/utils/basePath.ts)):
1. Check if path starts with `/spa` → use `/spa/`
2. Check for other path segments → use first segment
3. Fall back to `/` (root)

### 2. Configuration

[public/config.json](../public/config.json) includes a `basePath` setting:

```json
{
  "basePath": "auto",
  "apiBaseUrl": "/xsw/api"
}
```

Options:
- `"auto"` - Auto-detect from URL (recommended)
- `"/"` - Force root path
- `"/spa/"` - Force /spa path
- Custom - Any other path

### 3. Router Integration

Vue Router uses the detected base path automatically:

```typescript
// router/index.ts
const basePath = detectBasePath('auto');
const router = createRouter({
  history: createWebHistory(basePath),
  routes
});
```

## Deployment Scenarios

### Scenario 1: FastAPI Backend (Port 8000)

**Setup**: Frontend served by FastAPI from `/spa` path

**Access**: `http://localhost:8000/spa`

**Backend API**: `http://localhost:8000/xsw/api`

**Configuration**:
```bash
# Copy SPA config
cp public/config.spa.json public/config.json

# Or use auto-detection (default)
# basePath: "auto" in config.json
```

**Build**:
```bash
npm run build
# Outputs to: dist/spa/
```

**Deploy**:
```bash
# Backend serves from dist/spa/
# See: main_optimized.py lines 219-225
```

**Routing**:
- `/spa` → Vue SPA index.html
- `/spa/books/123` → Vue Router handles (client-side)
- `/xsw/api/*` → FastAPI backend endpoints

### Scenario 2: Standalone (Port 3000 or nginx)

**Setup**: Frontend served independently from root

**Access**: `http://localhost:3000/`

**Backend API**: `http://localhost:8000/xsw/api` (proxied or CORS)

**Configuration**:
```bash
# Copy root config
cp public/config.root.json public/config.json

# Or use auto-detection (default)
# basePath: "auto" in config.json
```

**Build**:
```bash
npm run build
# Outputs to: dist/spa/
```

**Deploy (nginx example)**:
```nginx
server {
  listen 80;
  root /app/dist/spa;

  location / {
    try_files $uri $uri/ /index.html;
  }

  location /xsw/api {
    proxy_pass http://backend:8000;
  }
}
```

**Routing**:
- `/` → Vue SPA index.html
- `/books/123` → Vue Router handles (client-side)
- `/xsw/api/*` → Proxied to backend

### Scenario 3: Custom Base Path

**Setup**: Frontend served from custom path (e.g., `/app/`)

**Access**: `http://localhost/app/`

**Configuration**:
```json
{
  "basePath": "/app/"
}
```

The auto-detection will recognize `/app/` and configure routing accordingly.

## Configuration Files

### Default Config (Auto-Detection)
[public/config.json](../public/config.json):
```json
{
  "basePath": "auto",
  "apiBaseUrl": "/xsw/api"
}
```

### FastAPI Deployment Config
[public/config.spa.json](../public/config.spa.json):
```json
{
  "basePath": "/spa/",
  "apiBaseUrl": "/xsw/api"
}
```

### Standalone Deployment Config
[public/config.root.json](../public/config.root.json):
```json
{
  "basePath": "/",
  "apiBaseUrl": "/xsw/api"
}
```

## Development

### Dev Server (npm run dev)

Auto-detects as root `/` since it runs on `http://localhost:9000/`

```bash
npm run dev
# Opens: http://localhost:9000/
# Base path: /
```

### Testing /spa Path Locally

To test the `/spa` path behavior:

```bash
# Option 1: Build and serve with FastAPI
npm run build
docker-compose up xsw
# Access: http://localhost:8000/spa

# Option 2: Configure a local server with /spa prefix
# (nginx, http-server, etc.)
```

## Build Process

### Single Build for All Deployments

No need for different builds! One build works everywhere:

```bash
npm run build
```

Output: `dist/spa/`

This build can be deployed to:
- FastAPI backend (`/spa` path) ✅
- Standalone nginx (`/` path) ✅
- Custom path deployment ✅

### Build Output Structure

```
dist/spa/
├── index.html
├── assets/
│   ├── *.js
│   ├── *.css
│   └── ...
├── icons/
├── config.json
├── config.spa.json
└── config.root.json
```

## How URLs Are Handled

### Example: Book Detail Page

**Frontend Route**: `/books/123`

**Deployment at `/` (root)**:
- URL: `http://localhost:3000/books/123`
- Router base: `/`
- Full route: `/books/123`

**Deployment at `/spa/`**:
- URL: `http://localhost:8000/spa/books/123`
- Router base: `/spa/`
- Full route: `/spa/books/123`

**Result**: Both work identically, URLs are automatically correct!

### Example: API Calls

API calls use relative URLs from `config.json`:

```typescript
// config.json: "apiBaseUrl": "/xsw/api"
api.get('/books/123')
// Calls: /xsw/api/books/123
```

This works regardless of frontend base path because API is always at `/xsw/api`.

## Asset Loading

Assets (JS, CSS, images) are loaded relative to base path:

**At `/spa/`**:
```html
<script src="/spa/assets/index.js"></script>
<link href="/spa/assets/index.css" rel="stylesheet">
```

**At `/`**:
```html
<script src="/assets/index.js"></script>
<link href="/assets/index.css" rel="stylesheet">
```

Vite handles this automatically when you set `base` in vite config.

## Troubleshooting

### Issue: 404 on Page Refresh

**Symptom**: Navigating to `/spa/books/123` directly returns 404

**Cause**: Server not configured for SPA routing

**Solution (FastAPI)**: Catch-all route already configured
```python
@app.get("/{full_path:path}")
async def serve_spa_catch_all(full_path: str):
    return FileResponse(spa_index_html)
```

**Solution (nginx)**:
```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

### Issue: Assets Not Loading

**Symptom**: JS/CSS files return 404

**Cause**: Base path mismatch

**Debug**:
```typescript
// In browser console:
import { getBasePathDebugInfo } from 'src/utils/basePath';
console.log(getBasePathDebugInfo());
```

**Solution**: Ensure config.json `basePath` matches deployment

### Issue: Wrong Base Path Detected

**Symptom**: App routes don't work, URLs are incorrect

**Cause**: Auto-detection confusion with route paths

**Solution**: Set explicit base path in config:
```json
{
  "basePath": "/spa/"
}
```

### Issue: API Calls Fail

**Symptom**: Network errors when calling backend

**Cause**: API base URL mismatch

**Debug**:
```bash
# Check what API base is being used
# In browser console:
console.log(appConfig.value.apiBaseUrl)
```

**Solution**: Update `apiBaseUrl` in config.json:
```json
{
  "apiBaseUrl": "/xsw/api"
}
```

## Migration Guide

### From Old Setup (Separate Builds)

**Before**: Different builds for different paths
```bash
# Build for /spa
PUBLIC_PATH=/spa npm run build

# Build for /
npm run build
```

**After**: Single build for all paths
```bash
# One build for everything
npm run build
```

**Changes Required**:
1. Update config.json with `"basePath": "auto"`
2. Remove any hardcoded base paths from code
3. Test both deployment scenarios

### From Hardcoded Base Path

**Before**:
```typescript
// router/index.ts
history: createWebHistory('/spa')
```

**After**:
```typescript
// router/index.ts
const basePath = detectBasePath('auto');
history: createWebHistory(basePath)
```

## Testing Checklist

Test the following scenarios:

### ✅ FastAPI Deployment (`/spa`)
- [ ] Navigate to `http://localhost:8000/spa`
- [ ] Homepage loads correctly
- [ ] Book list page works
- [ ] Direct navigation to `/spa/books/123` works
- [ ] Page refresh doesn't 404
- [ ] Assets (JS/CSS) load correctly
- [ ] API calls work
- [ ] Vue Router navigation works

### ✅ Standalone Deployment (`/`)
- [ ] Navigate to `http://localhost:3000/`
- [ ] Homepage loads correctly
- [ ] Book list page works
- [ ] Direct navigation to `/books/123` works
- [ ] Page refresh doesn't 404
- [ ] Assets (JS/CSS) load correctly
- [ ] API calls work (may need proxy)
- [ ] Vue Router navigation works

### ✅ Development (`npm run dev`)
- [ ] Dev server starts
- [ ] Hot reload works
- [ ] All routes accessible
- [ ] API calls work (with proxy)

## Advanced: Custom Base Path

For deployments at custom paths (e.g., `/myapp/`):

### 1. Update config.json
```json
{
  "basePath": "/myapp/",
  "apiBaseUrl": "/xsw/api"
}
```

### 2. Configure Server

**nginx**:
```nginx
location /myapp/ {
    alias /app/dist/spa/;
    try_files $uri $uri/ /myapp/index.html;
}
```

**FastAPI**:
```python
app.mount("/myapp", StaticFiles(directory=spa_dir), name="myapp")

@app.get("/myapp/{full_path:path}")
async def serve_myapp(full_path: str):
    return FileResponse(spa_index_html)
```

### 3. Test
```bash
# Access at custom path
http://localhost:8000/myapp/
```

## Summary

### Key Features
✅ **Runtime detection** - No rebuild needed for different paths
✅ **Auto-configuration** - Works out of the box
✅ **Manual override** - Can force specific base path
✅ **Universal build** - One build for all deployments
✅ **Debug tools** - Built-in debugging utilities

### Supported Deployments
- ✅ FastAPI backend (`/spa`)
- ✅ Standalone nginx (`/`)
- ✅ Custom paths
- ✅ Dev server
- ✅ Docker
- ✅ Any HTTP server

### Files Modified
- [src/router/index.ts](../src/router/index.ts) - Runtime base path detection
- [src/utils/basePath.ts](../src/utils/basePath.ts) - Detection utility
- [public/config.json](../public/config.json) - Added `basePath` setting
- [public/config.spa.json](../public/config.spa.json) - FastAPI config example
- [public/config.root.json](../public/config.root.json) - Standalone config example

### Related Documentation
- [SPA Serving Guide](SPA_SERVING.md) - FastAPI backend serving
- [Deployment Guide](../README.md#deployment) - General deployment instructions
