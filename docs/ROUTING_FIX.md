# API Routing Fix - 404 Errors Resolution

## Problem Summary

After deploying the application, API endpoints were returning 404 errors:
```
INFO: 10.98.128.222:56256 - "GET /xsw/api/categories HTTP/1.1" 404 Not Found
INFO: 172.18.0.1:43213 - "GET /xsw/api/health HTTP/1.1" 404 Not Found
```

All endpoints under `/xsw/api/*` were inaccessible, while the SPA frontend at `/` worked correctly.

## Root Causes

### 1. StaticFiles Mount Blocking All Routes

**The Critical Issue:**
```python
# WRONG - This was blocking all requests
app.mount("/", StaticFiles(directory=spa_dir, html=False), name="spa")
```

In FastAPI/Starlette, **mounts take precedence over routes**. When you mount StaticFiles at `/`, it intercepts ALL requests before any route handlers can be checked. This is because:

- Mounts are processed in middleware stack BEFORE route matching
- A mount at `/` captures every path: `/xsw/api/health`, `/categories`, everything
- Even though the static files don't exist, the mount returns 404 instead of letting routes handle the request

**Why This Happened:**
The original code attempted to use `html=False` to prevent auto-serving index.html, expecting routes to still work. However, the mount still captures all paths and returns 404 for non-existent files before routes are checked.

### 2. Incorrect Root Path Configuration

```python
# This only works behind a reverse proxy
app = FastAPI(root_path="/xsw/api")
```

The `root_path` parameter tells FastAPI that the app is mounted behind a proxy at `/xsw/api`. However:
- It doesn't automatically add `/xsw/api` prefix to your routes
- Routes were defined without the prefix (e.g., `@app.get("/health")`)
- This resulted in routes at `/health` instead of `/xsw/api/health`
- Without a reverse proxy stripping the prefix, direct access to `/xsw/api/health` returns 404

### 3. Router Inclusion Timing

```python
# WRONG - Router included before routes are defined
app.include_router(api_router, prefix="/xsw/api")

# ... routes defined here later
@api_router.get("/health")
def health():
    pass
```

FastAPI processes `include_router()` immediately. If routes are added to the router AFTER inclusion, they won't be registered with the app.

## The Solution

### Step 1: Create Dedicated APIRouter

```python
from fastapi import APIRouter

# Create router for all API endpoints
api_router = APIRouter()
```

This separates API routes from app-level routes (SPA serving, health checks).

### Step 2: Convert All API Routes

Changed all API endpoint decorators:
```python
# BEFORE
@app.get("/categories")
def get_categories():
    pass

# AFTER
@api_router.get("/categories")
def get_categories():
    pass
```

This was done for all 22+ API endpoints using replace-all:
- `@app.get` → `@api_router.get`
- `@app.post` → `@api_router.post`
- `@app.delete` → `@api_router.delete`

### Step 3: Fix Static File Serving

Removed the blocking root mount and replaced with selective mounts:

```python
if os.path.exists(spa_dir):
    INDEX_FILE = Path(spa_dir) / "index.html"

    # 1) Serve SPA root explicitly
    @app.get("/", include_in_schema=False)
    async def spa_root() -> FileResponse:
        return FileResponse(INDEX_FILE, media_type="text/html")

    # 2) Mount only specific static directories
    assets_dir = os.path.join(spa_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    icons_dir = os.path.join(spa_dir, "icons")
    if os.path.exists(icons_dir):
        app.mount("/icons", StaticFiles(directory=icons_dir), name="icons")

    # 3) Serve root-level static files with routes
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return FileResponse(os.path.join(spa_dir, "favicon.ico"))

    @app.get("/{filename}.{ext}", include_in_schema=False)
    async def spa_static_files(filename: str, ext: str):
        """Serve static files like config.json, opc.pem, etc."""
        filepath = os.path.join(spa_dir, f"{filename}.{ext}")
        if os.path.exists(filepath) and os.path.isfile(filepath):
            return FileResponse(filepath)
        raise HTTPException(status_code=404, detail="File not found")

    # 4) Keep SPA fallback middleware for client-side routing
    @app.middleware("http")
    async def spa_history_mode_fallback(request: Request, call_next):
        response = await call_next(request)

        if response.status_code != 404:
            return response

        path = request.url.path or ""

        # Don't intercept API paths
        if path.startswith("/xsw/api"):
            return response

        # Serve index.html for SPA routes (paths without file extensions)
        last_seg = path.rsplit("/", 1)[-1]
        if "." not in last_seg and INDEX_FILE.exists():
            return FileResponse(INDEX_FILE, media_type="text/html")

        return response
```

**Key Changes:**
- ✅ No mount at `/` - allows routes to be checked first
- ✅ Specific mounts at `/assets` and `/icons` only
- ✅ Route handlers for individual files (favicon, config.json)
- ✅ Middleware for SPA fallback AFTER route matching fails

### Step 4: Include Router at End of File

```python
# At the VERY END of main_optimized.py, after all routes are defined
# -----------------------
# Include API Router
# -----------------------
# IMPORTANT: This must be done AFTER all route definitions above
app.include_router(api_router, prefix="/xsw/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Why This Works:**
1. All routes are defined on `api_router` first (lines 290-1650)
2. Router inclusion happens at the very end (line 1702)
3. All routes are registered with the `/xsw/api` prefix
4. Routes take precedence over static file serving (no blocking mount)

## Request Flow After Fix

### API Request: `GET /xsw/api/health`

```
1. CORS Middleware ✓
2. Rate Limit Middleware ✓
3. Route Matching:
   - Check app routes (/, /healthz, etc.) ✗
   - Check included routers:
     - api_router with prefix "/xsw/api" ✓
       - Match: @api_router.get("/health") → /xsw/api/health ✓
4. Execute health() handler ✓
5. Return JSON response ✓
```

### SPA Route: `GET /books/123`

```
1. CORS Middleware ✓
2. Rate Limit Middleware ✓
3. Route Matching:
   - Check app routes (/, /healthz, etc.) ✗
   - Check included routers (api_router) ✗
   - Check static mounts (/assets, /icons) ✗
4. All routes return 404 ✓
5. SPA Fallback Middleware:
   - Path doesn't start with /xsw/api ✓
   - Path has no extension ("/books/123") ✓
   - Serve index.html ✓
6. Vue Router handles /books/123 client-side ✓
```

### Static Asset: `GET /assets/index-BWThQijL.js`

```
1. CORS Middleware ✓
2. Rate Limit Middleware ✓
3. Route Matching:
   - Check app routes ✗
   - Check included routers ✗
   - Check static mounts:
     - /assets mount ✓
       - File exists: /app/dist/spa/assets/index-BWThQijL.js ✓
4. Serve file from disk ✓
```

## Technical Details

### FastAPI Route Resolution Order

FastAPI checks requests in this order:
1. **Middleware** (in order added)
2. **Route Handlers** (including included routers)
3. **Mounts** (static files, sub-applications)
4. **Exception Handlers**

Our fix ensures:
- API routes are checked BEFORE static file serving
- Selective mounts only for specific paths
- Middleware fallback only after everything else fails

### Why `app.include_router()` Must Be Last

```python
# This is how FastAPI processes router inclusion:

api_router = APIRouter()

# Define routes on router
@api_router.get("/health")  # Adds route to api_router.routes list
def health():
    pass

# Include router - processes ALL routes in api_router.routes at this moment
app.include_router(api_router, prefix="/xsw/api")

# Too late - this won't be included!
@api_router.get("/categories")
def get_categories():
    pass
```

The `include_router()` call copies routes from the router to the app at that moment. Routes added later are not automatically registered.

### Mount vs. Route Priority

```python
# Mount takes precedence - WRONG
app.mount("/", StaticFiles(directory="dist"))
app.get("/api/health", handler)  # Never reached!

# Route takes precedence - CORRECT
app.get("/api/health", handler)  # Checked first
app.mount("/assets", StaticFiles(directory="dist/assets"))  # Specific path
```

## Testing the Fix

### Verify API Endpoints
```bash
# Health check
curl http://localhost:8000/xsw/api/health
# Expected: {"status": "ok", ...}

# Categories
curl http://localhost:8000/xsw/api/categories
# Expected: [{"name": "玄幻小說", ...}, ...]

# OpenAPI docs
curl http://localhost:8000/openapi.json | jq '.paths | keys[]' | grep "/xsw/api"
# Expected: List of all API endpoints with /xsw/api prefix
```

### Verify SPA Serving
```bash
# Root page
curl http://localhost:8000/
# Expected: HTML with <title>看小說</title>

# Client-side route (should serve index.html)
curl http://localhost:8000/books/123
# Expected: Same HTML as /

# Static assets
curl -I http://localhost:8000/assets/index-BWThQijL.js
# Expected: HTTP/1.1 200 OK

# Favicon
curl -I http://localhost:8000/favicon.ico
# Expected: HTTP/1.1 200 OK
```

## Lessons Learned

### 1. Mount Path Priority
- Never mount StaticFiles at `/` in an app with API routes
- Use selective mounts for specific directories (`/assets`, `/icons`)
- Let routes handle most paths, use mounts for static-only directories

### 2. FastAPI Router Pattern
- Define all routes on router FIRST
- Include router LAST (after all route definitions)
- Use prefixes to organize API paths

### 3. SPA + API Architecture
The correct structure:
```
app (FastAPI)
├── Middleware (CORS, Rate Limit)
├── Routes (SPA root, health checks)
├── Included Routers
│   └── api_router with prefix="/xsw/api"
│       ├── /xsw/api/health
│       ├── /xsw/api/categories
│       └── ... (all API endpoints)
├── Selective Mounts
│   ├── /assets → StaticFiles(spa/assets)
│   └── /icons → StaticFiles(spa/icons)
└── SPA Fallback Middleware
```

### 4. Debugging Tips
- Check OpenAPI docs: `curl http://localhost:8000/openapi.json | jq '.paths | keys'`
- Verify route registration: All API paths should have `/xsw/api` prefix
- Test in order: health → simple GET → complex POST → static files → SPA

## Related Files

- **[main_optimized.py](../main_optimized.py)** - Main application file
  - Line 169: APIRouter creation
  - Lines 230-286: SPA static file serving
  - Lines 290-1650: API route definitions
  - Line 1702: Router inclusion
- **[CLAUDE.md](../CLAUDE.md)** - Project documentation (should be updated)

## Additional Changes in This Session

### 1. Pip Cache in Docker

Added pip caching similar to npm in [docker/Dockerfile:25](../docker/Dockerfile#L25):
```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt && \
    pip install ruff
```

This speeds up rebuilds by caching downloaded packages.

### 2. AUTH_ENABLED Environment Variable

Added authentication control in [auth.py:17](../auth.py#L17):
```python
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"
```

Usage:
```bash
# Disable authentication for development
export AUTH_ENABLED=false
uvicorn main_optimized:app --reload

# Or in docker-compose
AUTH_ENABLED=false docker compose up
```

When disabled:
- All admin endpoints are accessible without JWT tokens
- Admin user initialization is skipped
- Useful for local development and testing

## Deployment Notes

### Docker Build
The fix is included in the Docker image. Rebuild with:
```bash
docker compose -f compose.yml -f docker/build.yml up -d --build
```

### Environment Variables
```bash
# Required
BASE_URL=https://m.xsw.tw

# Optional
AUTH_ENABLED=false  # Disable authentication (default: true)
```

### Verification
After deployment, verify all endpoints are accessible:
```bash
# Check health
curl https://your-domain.com/xsw/api/health

# Check categories
curl https://your-domain.com/xsw/api/categories

# Check SPA
curl https://your-domain.com/
```

## Summary

**Problem**: API routes were inaccessible (404 errors) due to StaticFiles mount at `/` blocking all requests.

**Solution**:
1. Created APIRouter for all API endpoints
2. Removed root-level StaticFiles mount
3. Used selective mounts only for static directories
4. Included router at end of file with `/xsw/api` prefix

**Result**: All API endpoints work correctly, SPA serves properly, static assets load successfully.

---

**Date**: February 1, 2026
**Fixed By**: Claude Code
**Related Issue**: Container logs showing 404 for /xsw/api/* endpoints
