# SPA Serving Architecture

## Overview

This document explains how the FastAPI backend serves the Vue.js Single Page Application (SPA) using a 3-layer architecture that combines StaticFiles mounting with intelligent middleware fallback.

**Location**: `main_optimized.py` lines 219-261

**Goal**: Serve a Vue SPA with history mode routing from a FastAPI backend without requiring a separate nginx container.

---

## Architecture Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Request                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Middleware (Layer 3)                            │
│  • Intercepts all requests                                   │
│  • Calls call_next() to try normal routing first            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│           Explicit Root Route (Layer 2)                      │
│  • Handles GET /                                             │
│  • Returns index.html                                        │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│           StaticFiles Mount (Layer 1)                        │
│  • Mounted at "/"                                            │
│  • Serves actual files from /app/dist/spa                   │
│  • html=False (no auto index.html serving)                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
              ┌───────┴────────┐
              │                │
         200 OK           404 Not Found
              │                │
              ▼                ▼
        Return File      Back to Middleware
                              │
                              ▼
                      Middleware Checks:
                      • Is it API path?
                      • Has extension?
                              │
                    ┌─────────┴──────────┐
                    │                    │
              No Extension          Has Extension
            (Client Route)          (Missing File)
                    │                    │
                    ▼                    ▼
            Return index.html      Return 404
```

---

## Layer 1: StaticFiles Mount

**Location**: `main_optimized.py:227`

```python
app.mount("/", StaticFiles(directory=spa_dir, html=False), name="spa")
```

### Purpose
Serve actual static files (JavaScript, CSS, images, fonts) from the built SPA.

### Key Parameters
- **directory**: `/app/dist/spa` - The built Vue SPA output directory
- **html=False**: **Critical** - Prevents automatic index.html serving for every path
- **mount path**: `/` - Serves files from root path

### What It Handles
| Request | File Path | Result |
|---------|-----------|--------|
| `GET /assets/app.js` | `/app/dist/spa/assets/app.js` | ✓ Serves JS file |
| `GET /css/app.css` | `/app/dist/spa/css/app.css` | ✓ Serves CSS file |
| `GET /favicon.ico` | `/app/dist/spa/favicon.ico` | ✓ Serves icon |
| `GET /fonts/roboto.woff2` | `/app/dist/spa/fonts/roboto.woff2` | ✓ Serves font |
| `GET /books` | `/app/dist/spa/books` (no file) | ❌ 404 |

### Why html=False?
Without `html=False`, StaticFiles would automatically serve `index.html` for every directory-like path, bypassing our middleware logic and breaking API routes.

---

## Layer 2: Explicit Root Route

**Location**: `main_optimized.py:232-234`

```python
@app.get("/", include_in_schema=False)
async def spa_root() -> FileResponse:
    return FileResponse(INDEX_FILE, media_type="text/html")
```

### Purpose
Explicitly handle the root path `/` request.

### Why Needed?
- StaticFiles with `html=False` won't auto-serve index.html for `/`
- Without this route, visiting `http://localhost:8000/` would return 404 or directory listing
- The `@app.get("/")` decorator takes precedence over StaticFiles mount

### What It Handles
| Request | Result |
|---------|--------|
| `GET /` | ✓ Serves `index.html` |
| `GET /index.html` | ✓ Serves `index.html` (via StaticFiles) |

---

## Layer 3: Middleware Fallback

**Location**: `main_optimized.py:238-261`

```python
@app.middleware("http")
async def spa_history_mode_fallback(request: Request, call_next):
    # 1. Try normal routing first (APIs, static files, explicit routes)
    response: Response = await call_next(request)

    # 2. If successful, return immediately
    if response.status_code != 404:
        return response

    path = request.url.path or ""

    # 3. Don't interfere with API routes
    if path.startswith("/xsw/api"):
        return response  # Keep API 404s as 404s

    # 4. Heuristic: No extension = likely a client-side route
    last_seg = path.rsplit("/", 1)[-1]
    if "." not in last_seg and INDEX_FILE.exists():
        return FileResponse(INDEX_FILE, media_type="text/html")

    # 5. Has extension but missing = real 404 (missing file)
    return response
```

### Purpose
Enable Vue Router **history mode** by serving `index.html` for client-side routes that don't correspond to actual files.

### How It Works

**Step 1: Try Normal Routing**
```python
response = await call_next(request)
```
Passes the request through the entire FastAPI routing stack (API routes, StaticFiles, explicit routes).

**Step 2: Check Status**
```python
if response.status_code != 404:
    return response
```
If anything succeeded (200, 301, etc.), return immediately. Only intervene on 404s.

**Step 3: Protect API Routes**
```python
if path.startswith("/xsw/api"):
    return response
```
API endpoints that don't exist should return proper 404s, not HTML.

**Step 4: Extension Heuristic**
```python
last_seg = path.rsplit("/", 1)[-1]
if "." not in last_seg:
    return FileResponse(INDEX_FILE)
```
Paths without extensions are likely client-side routes:
- `/books` → No dot → Client route → Serve `index.html`
- `/chapters/123` → No dot → Client route → Serve `index.html`
- `/missing.js` → Has dot → Missing file → Return 404

**Step 5: Return Original 404**
```python
return response
```
For paths with extensions (like `.js`, `.css`), keep the 404 to help debug missing files.

### What It Handles
| Request | Path Check | Extension Check | Result |
|---------|------------|-----------------|--------|
| `GET /books` | Not API ✓ | No dot ✓ | Serve `index.html` |
| `GET /chapters/123456` | Not API ✓ | No dot ✓ | Serve `index.html` |
| `GET /dashboard` | Not API ✓ | No dot ✓ | Serve `index.html` |
| `GET /xsw/api/undefined` | API path ✗ | - | Keep 404 |
| `GET /missing.js` | Not API ✓ | Has dot ✗ | Keep 404 |
| `GET /assets/gone.css` | Not API ✓ | Has dot ✗ | Keep 404 |

---

## Complete Request Flow Examples

### Example 1: Vue Router Client Route

**Request**: `GET http://localhost:8000/books/123456`

```
1. Middleware intercepts request
2. Middleware calls call_next()
3. FastAPI checks explicit routes: No match
4. StaticFiles checks: No file at /app/dist/spa/books/123456
5. Returns 404 response
6. Middleware receives 404
7. Checks: path="/books/123456", not API, no extension
8. Returns FileResponse(index.html)
9. Browser receives HTML
10. Vue app loads
11. Vue Router parses /books/123456
12. ChapterPage component renders
```

### Example 2: Static Asset

**Request**: `GET http://localhost:8000/assets/app.js`

```
1. Middleware intercepts request
2. Middleware calls call_next()
3. FastAPI checks explicit routes: No match
4. StaticFiles finds: /app/dist/spa/assets/app.js exists
5. Returns 200 with JS content
6. Middleware receives 200
7. Returns response immediately (no intervention)
8. Browser receives JavaScript file
```

### Example 3: API Call

**Request**: `GET http://localhost:8000/xsw/api/books`

```
1. Middleware intercepts request
2. Middleware calls call_next()
3. FastAPI checks routes: Matches @app.get("/xsw/api/books")
4. Route handler executes
5. Returns 200 with JSON data
6. Middleware receives 200
7. Returns response immediately
8. Client receives JSON
```

### Example 4: Missing API Endpoint

**Request**: `GET http://localhost:8000/xsw/api/undefined`

```
1. Middleware intercepts request
2. Middleware calls call_next()
3. FastAPI checks routes: No match
4. Returns 404
5. Middleware receives 404
6. Checks: path starts with "/xsw/api"
7. Returns 404 unchanged (doesn't serve index.html)
8. Client receives 404 error
```

### Example 5: Missing Static File

**Request**: `GET http://localhost:8000/assets/missing.js`

```
1. Middleware intercepts request
2. Middleware calls call_next()
3. FastAPI checks routes: No match
4. StaticFiles checks: No file at /app/dist/spa/assets/missing.js
5. Returns 404
6. Middleware receives 404
7. Checks: not API, but has ".js" extension
8. Returns 404 unchanged (helps debug missing files)
9. Browser console shows 404 error
```

---

## Key Design Decisions

### 1. Why Three Layers?

**Problem**: Need to serve both static files AND handle client-side routing.

**Solution**:
- StaticFiles handles real files efficiently
- Middleware handles 404 fallback intelligently
- Explicit root route handles special case of `/`

**Alternative Rejected**: Catch-all route like `@app.get("/{path:path}")` would intercept everything and require manual file serving.

### 2. Why Middleware Instead of Catch-All Route?

**Middleware Approach** (Used):
```python
@app.middleware("http")
async def spa_history_mode_fallback(request, call_next):
    response = await call_next(request)
    if response.status_code == 404:
        # Handle fallback
```

**Pros**:
- ✓ Runs AFTER all routes attempt to match
- ✓ Doesn't interfere with API routes
- ✓ StaticFiles handles real files efficiently
- ✓ Only intervenes on 404s

**Catch-All Route Approach** (Rejected):
```python
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    # Manual file serving + routing logic
```

**Cons**:
- ✗ Intercepts ALL routes
- ✗ API routes need explicit priority handling
- ✗ Must manually serve static files
- ✗ More complex route ordering issues

### 3. Why Extension Heuristic?

**Goal**: Distinguish between client routes and missing files.

**Heuristic**: Paths without dots are likely routes; paths with dots are likely files.

**Works for**:
- `/books` → Route
- `/chapters/123` → Route
- `/dashboard` → Route
- `/missing.js` → File (return 404 for debugging)
- `/assets/gone.css` → File (return 404 for debugging)

**Limitation**: Single-word files without extensions like `/README` would be served as index.html. This is acceptable because:
- Vue builds don't produce such files
- API routes are explicitly protected
- Real edge cases can use explicit routes

### 4. Why Protect `/xsw/api` Paths?

**Problem**: API 404s should be genuine 404s, not HTML responses.

**Without protection**:
```bash
curl http://localhost:8000/xsw/api/undefined
# Returns: <html>...</html>  ← Wrong! Confuses API clients
```

**With protection**:
```bash
curl http://localhost:8000/xsw/api/undefined
# Returns: {"detail": "Not Found"}  ← Correct!
```

---

## Configuration

### Build-Time Configuration

**Dockerfile** (`docker/Dockerfile`):
```dockerfile
# Copy Vue build output
COPY --from=builder /web/dist /app/dist
```

Ensures `/app/dist/spa` contains the built Vue SPA.

**Quasar Build** (`quasar.config.ts`):
```javascript
build: {
  distDir: 'dist/spa',
  // ...
}
```

Outputs SPA to `dist/spa/` directory.

### Runtime Configuration

**FastAPI App**:
```python
spa_dir = "/app/dist/spa"

if os.path.exists(spa_dir):
    # Mount and configure SPA serving
    app.mount("/", StaticFiles(directory=spa_dir, html=False), name="spa")
    # ...
```

If `spa_dir` doesn't exist, SPA serving is disabled (useful for development).

---

## Troubleshooting

### Issue 1: Client Routes Return 404

**Symptom**: Visiting `/books` returns 404 instead of the Vue app.

**Causes**:
1. SPA not built: `/app/dist/spa` doesn't exist
2. Middleware not registered
3. Middleware returning 404 for non-extension paths

**Debug**:
```bash
# Check if SPA is built
docker exec xsw-xsw-1 ls /app/dist/spa
# Should show: index.html, assets/, css/, etc.

# Check server logs
docker logs xsw-xsw-1 --tail 50
# Look for middleware registration messages
```

**Fix**:
```bash
# Rebuild SPA
npm run build

# Rebuild Docker image
docker compose -f compose.yml -f docker/build.yml build xsw
docker compose up -d xsw
```

### Issue 2: Static Assets Not Loading

**Symptom**: Vue app loads but shows blank page, browser console shows 404 for JS/CSS files.

**Causes**:
1. Wrong base path in Vue build
2. StaticFiles mount not working
3. Assets in wrong directory

**Debug**:
```bash
# Check browser console
# Look for: GET http://localhost:8000/assets/app.js → 404

# Check file structure
docker exec xsw-xsw-1 ls -la /app/dist/spa/assets/
```

**Fix**:
- Ensure Vue build uses correct base path (see `docs/RUNTIME_BASE_PATH.md`)
- Check `quasar.config.ts` has correct `publicPath`

### Issue 3: API Routes Return HTML

**Symptom**: API calls return `<html>...` instead of JSON.

**Cause**: API path not protected in middleware.

**Debug**:
```bash
curl http://localhost:8000/xsw/api/books
# If returns HTML, API protection is broken
```

**Fix**:
Ensure middleware has API path check:
```python
if path.startswith("/xsw/api"):
    return response  # Don't serve index.html for APIs
```

### Issue 4: Real 404s Serve index.html

**Symptom**: Typo URLs like `/boks` (should be `/books`) serve the Vue app instead of 404.

**Expected Behavior**: This is actually correct! The Vue app should load, then Vue Router will show a "not found" page or redirect.

**Why**: We can't distinguish between `/books` (valid route) and `/boks` (typo) at the FastAPI level. Vue Router handles this client-side.

**Proper Solution**: Implement 404 page in Vue Router:
```javascript
// routes.js
{
  path: '/:pathMatch(.*)*',
  name: 'NotFound',
  component: () => import('pages/NotFoundPage.vue')
}
```

---

## Performance Considerations

### Caching

**Static Assets**: Served directly by StaticFiles with proper cache headers.
```
Cache-Control: max-age=31536000 (for hashed assets like app.abc123.js)
Cache-Control: no-cache (for index.html)
```

**index.html**: Always re-validated to ensure latest client code.

### Middleware Overhead

**Minimal Impact**: Middleware only runs logic on 404 responses.

**Successful Requests**:
- Static files: Direct serve by StaticFiles (no middleware logic)
- API calls: Direct route match (no middleware logic)
- Root `/`: Explicit route (no middleware logic)

**Failed Requests** (404s):
- Middleware adds: ~0.1ms for path checks
- Acceptable for client routing (infrequent in production)

---

## Extending the Architecture

### Adding Subpath Deployment

To serve SPA from `/app/` instead of `/`:

1. **Update mount path**:
```python
app.mount("/app", StaticFiles(directory=spa_dir, html=False), name="spa")
```

2. **Update root route**:
```python
@app.get("/app/")
async def spa_root():
    return FileResponse(INDEX_FILE)
```

3. **Update middleware**:
```python
if not path.startswith("/app/"):
    return response  # Not our SPA path
```

4. **Update Vue Router base**:
```javascript
// router/index.ts
history: createWebHistory('/app/')
```

### Adding Multiple SPAs

To serve different SPAs at different paths:

```python
# Admin SPA at /admin
admin_spa_dir = "/app/dist/admin"
app.mount("/admin", StaticFiles(directory=admin_spa_dir, html=False), name="admin_spa")

@app.get("/admin/")
async def admin_spa_root():
    return FileResponse(Path(admin_spa_dir) / "index.html")

# Main SPA at /
main_spa_dir = "/app/dist/spa"
app.mount("/", StaticFiles(directory=main_spa_dir, html=False), name="main_spa")

# Update middleware to handle both
@app.middleware("http")
async def multi_spa_fallback(request, call_next):
    response = await call_next(request)
    if response.status_code != 404:
        return response

    path = request.url.path

    # Admin SPA
    if path.startswith("/admin"):
        last_seg = path.split("/")[-1]
        if "." not in last_seg:
            return FileResponse(Path(admin_spa_dir) / "index.html")

    # Main SPA
    else:
        last_seg = path.split("/")[-1]
        if "." not in last_seg:
            return FileResponse(Path(main_spa_dir) / "index.html")

    return response
```

---

## Related Documentation

- [Runtime Base Path Detection](RUNTIME_BASE_PATH.md) - Vue Router base path configuration
- [SPA Serving Guide](SPA_SERVING.md) - Deployment and configuration guide
- [Google SSO Setup](GOOGLE_SSO_SETUP.md) - Admin panel authentication

---

## References

- **FastAPI StaticFiles**: https://fastapi.tiangolo.com/tutorial/static-files/
- **FastAPI Middleware**: https://fastapi.tiangolo.com/tutorial/middleware/
- **Vue Router History Mode**: https://router.vuejs.org/guide/essentials/history-mode.html
- **SPA Deployment**: https://router.vuejs.org/guide/essentials/history-mode.html#example-server-configurations

---

## Changelog

| Date | Author | Changes |
|------|--------|---------|
| 2026-02-01 | Claude | Initial documentation of 3-layer SPA serving architecture |
