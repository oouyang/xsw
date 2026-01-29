# SPA Serving Configuration

This document explains how the Vue SPA is served from the FastAPI backend.

## Overview

The Vue.js Single Page Application (SPA) is served directly by the FastAPI backend on port 8000, eliminating the need for a separate web server.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              FastAPI Backend (Port 8000)             │
├─────────────────────────────────────────────────────┤
│                                                       │
│  ┌──────────────────┐    ┌──────────────────────┐  │
│  │   API Routes     │    │   SPA Serving        │  │
│  │  /xsw/api/*      │    │   / (root)           │  │
│  │                  │    │   /{any_path}        │  │
│  └──────────────────┘    └──────────────────────┘  │
│                                                       │
│  ┌──────────────────────────────────────────────┐  │
│  │   Static Assets Mount                         │  │
│  │   /spa/* → /app/dist/spa/*                   │  │
│  │   (JS, CSS, fonts, images)                   │  │
│  └──────────────────────────────────────────────┘  │
│                                                       │
└─────────────────────────────────────────────────────┘
```

## Route Handling

### 1. API Routes (`/xsw/api/*`)
- **Handled by**: FastAPI with `root_path="/xsw/api"`
- **Examples**:
  - `/xsw/api/health` - Health check
  - `/xsw/api/books/{id}` - Book details
  - `/xsw/api/search?q=keyword` - Search
  - `/xsw/api/admin/*` - Admin endpoints (JWT protected)

### 2. Static Assets (`/spa/*`)
- **Handled by**: `StaticFiles` mount
- **Source**: `/app/dist/spa/` directory
- **Examples**:
  - `/spa/assets/*.js` - JavaScript bundles
  - `/spa/assets/*.css` - Stylesheets
  - `/spa/fonts/*` - Font files
  - `/spa/img/*` - Images

### 3. SPA Routes (Everything Else)
- **Handled by**: Catch-all route serving `index.html`
- **Enables**: Vue Router client-side routing (History mode)
- **Examples**:
  - `/` - Home page (serves index.html)
  - `/books/123` - Book detail page (serves index.html)
  - `/books/123/chapters/45` - Chapter page (serves index.html)
  - `/dashboard` - Dashboard (serves index.html)

## Implementation Details

### FastAPI Configuration

```python
# Mount SPA static files (assets, js, css)
spa_dir = "/app/dist/spa"
spa_index_html = os.path.join(spa_dir, "index.html")

if os.path.exists(spa_dir):
    # Mount static assets under /spa (js, css, fonts, etc.)
    app.mount("/spa", StaticFiles(directory=spa_dir, html=False), name="spa")

# Root route - serves Vue SPA
@app.get("/")
async def serve_spa_root():
    if spa_index_html and os.path.exists(spa_index_html):
        return FileResponse(spa_index_html)
    return {"message": "Vue SPA not found. Build first with 'npm run build'"}

# Catch-all route - handles Vue Router client-side routing
@app.get("/{full_path:path}")
async def serve_spa_catch_all(full_path: str):
    # Don't intercept API routes
    if full_path.startswith("xsw/api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")

    # Serve index.html for all SPA routes
    if spa_index_html and os.path.exists(spa_index_html):
        return FileResponse(spa_index_html)

    raise HTTPException(status_code=404, detail="Vue SPA not built")
```

### Vue Router Configuration

The Vue app uses **History mode** (not hash mode):

```typescript
// quasar.config.ts
vueRouterMode: 'history'
```

This provides clean URLs without the `#` hash:
- ✅ `/books/123` (History mode)
- ❌ `/#/books/123` (Hash mode)

### API Base URL

The Vue app is configured to use the same origin for API calls:

```json
// public/config.json
{
  "apiBaseUrl": "/xsw/api"
}
```

This means API calls from the frontend use relative paths:
- Frontend: `http://localhost:8000/`
- API calls: `http://localhost:8000/xsw/api/*`

## Build Process

### Local Development

```bash
# Frontend dev server (hot reload)
npm run dev  # http://localhost:9000

# Backend dev server
uvicorn main_optimized:app --reload --port 8000
```

### Production Build

```bash
# Build the Vue SPA
npm run build  # Output: dist/spa/

# The built files are automatically copied in Docker:
COPY --from=builder /web/dist /app/dist
```

## Docker Deployment

### Single Container Setup

```yaml
# compose.yml
services:
  xsw:
    image: ${img}:${tag}
    ports:
      - 8000:8000  # Both API and SPA served on this port
    volumes:
      - xsw_data:/app/data
```

**Access**:
- Frontend: http://localhost:8000/
- API: http://localhost:8000/xsw/api/
- API Docs: http://localhost:8000/xsw/api/docs

### Dual Container Setup (Optional)

The original setup includes a separate nginx container:

```yaml
services:
  web:  # Separate nginx for SPA (optional)
    ports:
      - 2345:80

  xsw:  # FastAPI with integrated SPA
    ports:
      - 8000:8000
```

**Access**:
- Frontend (nginx): http://localhost:2345/
- Frontend (FastAPI): http://localhost:8000/
- API: http://localhost:8000/xsw/api/

## Troubleshooting

### Issue 1: 404 on Page Refresh

**Symptom**: Refreshing `/books/123` returns 404

**Cause**: Web server doesn't serve index.html for SPA routes

**Solution**: ✅ Already fixed with catch-all route

### Issue 2: API Calls Failing

**Symptom**: API calls return 404 or CORS errors

**Cause**: Incorrect `apiBaseUrl` in config.json

**Solution**: Ensure `apiBaseUrl` is set to `/xsw/api`

```json
{
  "apiBaseUrl": "/xsw/api"  // Relative path
}
```

### Issue 3: Assets Not Loading

**Symptom**: JavaScript/CSS files return 404

**Cause**: Incorrect asset paths or missing build

**Solution**:
1. Verify build exists: `ls -la dist/spa/`
2. Check asset paths in `dist/spa/index.html` (should be `/spa/assets/*`)
3. Rebuild: `npm run build`

### Issue 4: Vue SPA Not Found

**Symptom**: Root URL shows "Vue SPA not found" message

**Cause**: SPA not built or not copied to Docker image

**Solution**:
1. Build frontend: `npm run build`
2. Verify: `ls -la dist/spa/index.html`
3. Rebuild Docker: `docker-compose up -d --build`

## Development vs Production

### Development Mode

**Frontend** (hot reload, separate server):
```bash
npm run dev  # Port 9000
```

**Backend**:
```bash
uvicorn main_optimized:app --reload --port 8000
```

**Configuration**:
```json
// public/config.json (development)
{
  "apiBaseUrl": "http://localhost:8000/xsw/api"
}
```

### Production Mode

**Both served from single container**:
```bash
docker-compose up -d --build
```

**Configuration**:
```json
// public/config.json (production)
{
  "apiBaseUrl": "/xsw/api"  // Relative path
}
```

## Benefits of Integrated Serving

1. **Simpler Deployment**: Single container for both frontend and backend
2. **No CORS Issues**: Same origin for API and SPA
3. **Easier Configuration**: No need for nginx reverse proxy
4. **Lower Resource Usage**: One less container to run
5. **Unified Logging**: All logs in one place
6. **Simplified SSL**: Single certificate for both API and frontend

## Performance Considerations

### Static File Caching

FastAPI's `StaticFiles` automatically handles:
- ETag headers
- Last-Modified headers
- If-None-Match / If-Modified-Since checks

### Compression

For production, consider adding compression middleware:

```python
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

### CDN Integration

For high-traffic production:
1. Build with CDN URLs: `npm run build`
2. Upload `dist/spa/assets/*` to CDN
3. Update asset paths in index.html
4. Keep index.html served by FastAPI (for routing)

## Migration Notes

### From Separate nginx Container

If migrating from the separate `web` container:

1. **Update API calls** (if needed):
   - Old: `http://backend:8000/xsw/api/*`
   - New: `/xsw/api/*` (relative)

2. **Update Docker Compose**:
   - Remove `web` service (optional)
   - Access on port 8000 instead of 2345

3. **Update nginx reverse proxy** (if used):
   ```nginx
   # Old (separate containers)
   location / {
       proxy_pass http://web:80;
   }
   location /xsw/api {
       proxy_pass http://xsw:8000;
   }

   # New (single container)
   location / {
       proxy_pass http://xsw:8000;
   }
   ```

## Testing

### Manual Testing

1. **Root URL**: http://localhost:8000/
   - Should load Vue app home page

2. **SPA Route**: http://localhost:8000/books/123
   - Should load Vue app book detail page

3. **API Route**: http://localhost:8000/xsw/api/health
   - Should return JSON: `{"status": "ok", ...}`

4. **Static Asset**: http://localhost:8000/spa/assets/index.js
   - Should serve JavaScript file

5. **Refresh SPA Route**: Navigate to `/books/123`, then refresh
   - Should still load Vue app (not 404)

### Automated Testing

```bash
# Test API
curl http://localhost:8000/xsw/api/health

# Test SPA root
curl -I http://localhost:8000/
# Should return 200 with Content-Type: text/html

# Test SPA catch-all
curl -I http://localhost:8000/books/123
# Should return 200 with Content-Type: text/html

# Test static assets
curl -I http://localhost:8000/spa/assets/index.js
# Should return 200 with Content-Type: application/javascript
```

## Security Considerations

### Content Security Policy (CSP)

Consider adding CSP headers for production:

```python
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.endswith(('.html', '/')):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://accounts.google.com; "
            "style-src 'self' 'unsafe-inline';"
        )
    return response
```

### Static File Security

- ✅ `html=False` prevents directory listing
- ✅ Static files served without code execution
- ✅ Assets properly cached by browser

## References

- [FastAPI StaticFiles](https://fastapi.tiangolo.com/tutorial/static-files/)
- [Vue Router History Mode](https://router.vuejs.org/guide/essentials/history-mode.html)
- [Quasar SPA Build](https://quasar.dev/quasar-cli-vite/developing-spa/build-commands)
