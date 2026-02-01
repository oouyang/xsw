# Routing Architecture Overview

Quick reference for understanding the FastAPI routing structure in this project.

## Architecture Diagram

```
HTTP Request
    ↓
┌─────────────────────────────────────────────────────┐
│ FastAPI Application (main_optimized.py)             │
├─────────────────────────────────────────────────────┤
│                                                      │
│  1. MIDDLEWARE LAYER                                │
│     ├─ CORS Middleware                              │
│     ├─ Rate Limiting Middleware                     │
│     └─ SPA Fallback Middleware (runs last)          │
│                                                      │
│  2. ROUTE HANDLERS (checked first)                  │
│     ├─ @app.get("/")              → index.html      │
│     ├─ @app.get("/healthz")       → health check    │
│     ├─ @app.get("/favicon.ico")   → favicon         │
│     └─ @app.get("/{file}.{ext}")  → static files    │
│                                                      │
│  3. INCLUDED ROUTERS                                │
│     └─ api_router (prefix="/xsw/api")               │
│        ├─ @api_router.get("/health")                │
│        ├─ @api_router.get("/categories")            │
│        ├─ @api_router.get("/books/{book_id}")       │
│        └─ ... (all API endpoints)                   │
│                                                      │
│  4. STATIC FILE MOUNTS (selective paths only)       │
│     ├─ /assets → StaticFiles(spa/assets)            │
│     └─ /icons  → StaticFiles(spa/icons)             │
│                                                      │
└─────────────────────────────────────────────────────┘
         ↓
    Response
```

## Request Flow Examples

### API Request: `/xsw/api/health`

```
1. Request arrives
2. CORS middleware ✓
3. Rate limit middleware ✓
4. Check app routes → No match
5. Check included routers:
   - api_router (prefix="/xsw/api") ✓
     - Match: "/health" → "/xsw/api/health" ✓
6. Execute health() handler
7. Return JSON response
```

### SPA Client Route: `/books/123`

```
1. Request arrives
2. CORS middleware ✓
3. Rate limit middleware ✓
4. Check app routes → No match
5. Check included routers → No match
6. Check static mounts → No match
7. All return 404
8. SPA Fallback Middleware:
   - Not an API path ✓
   - No file extension ✓
   - Serve index.html ✓
9. Vue Router handles /books/123
```

### Static Asset: `/assets/index.js`

```
1. Request arrives
2. CORS middleware ✓
3. Rate limit middleware ✓
4. Check app routes → No match
5. Check included routers → No match
6. Check static mounts:
   - /assets mount ✓
   - File exists ✓
7. Serve file from disk
```

## Code Structure

### File: main_optimized.py

```python
# Line ~10: Imports
from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles

# Line ~140: Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database, cache, auth
    yield

# Line ~161: Create FastAPI app (NO root_path!)
app = FastAPI(
    title="看小說 API",
    lifespan=lifespan
)

# Line ~169: Create API router
api_router = APIRouter()

# Line ~207: Add middleware
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CORSMiddleware, ...)

# Line ~224: App-level routes
@app.get("/healthz")
def healthz():
    return {"ok": True}

# Line ~230: Selective static file serving
if os.path.exists(spa_dir):
    @app.get("/")
    async def spa_root():
        return FileResponse(INDEX_FILE)

    app.mount("/assets", StaticFiles(...))
    app.mount("/icons", StaticFiles(...))

    @app.get("/{filename}.{ext}")
    async def spa_static_files(filename, ext):
        return FileResponse(...)

    @app.middleware("http")
    async def spa_history_mode_fallback(request, call_next):
        # Fallback to index.html for SPA routes
        pass

# Line ~290: Define API routes (NOT included yet)
@api_router.get("/health")
def health():
    return {"status": "ok"}

@api_router.get("/categories")
def get_categories():
    # ... all API endpoints defined here
    pass

# ... more routes ...

# Line ~1702: Include router at END
app.include_router(api_router, prefix="/xsw/api")

# Line ~1705: Main
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Key Rules

### ✅ DO

1. **Define routes on `api_router`**
   ```python
   @api_router.get("/endpoint")
   def my_handler():
       pass
   ```

2. **Include router at the END**
   ```python
   # After all route definitions
   app.include_router(api_router, prefix="/xsw/api")
   ```

3. **Use selective static mounts**
   ```python
   app.mount("/assets", StaticFiles(directory="spa/assets"))
   ```

4. **Check routes before mounts**
   - Routes are checked before static file mounts
   - This allows API endpoints to work

### ❌ DON'T

1. **Don't mount StaticFiles at root**
   ```python
   # WRONG - blocks all routes!
   app.mount("/", StaticFiles(directory="spa"))
   ```

2. **Don't use @app decorators for API routes**
   ```python
   # WRONG - should use @api_router
   @app.get("/categories")
   def get_categories():
       pass
   ```

3. **Don't include router before defining routes**
   ```python
   # WRONG - router empty at this point
   app.include_router(api_router, prefix="/xsw/api")

   @api_router.get("/health")  # Too late!
   def health():
       pass
   ```

4. **Don't use root_path without proxy**
   ```python
   # WRONG - only works behind reverse proxy
   app = FastAPI(root_path="/xsw/api")
   @app.get("/health")  # Won't match /xsw/api/health
   ```

## Testing

### Verify Routing Works

```bash
# Test API endpoints
curl http://localhost:8000/xsw/api/health
curl http://localhost:8000/xsw/api/categories

# Test SPA root
curl http://localhost:8000/ | grep "<title>"

# Test static assets
curl -I http://localhost:8000/assets/index.js

# Test SPA fallback (should return HTML)
curl http://localhost:8000/books/123 | grep "<title>"

# Check OpenAPI docs
curl http://localhost:8000/openapi.json | jq '.paths | keys | .[]'
```

### Expected Results

All API endpoints should have `/xsw/api` prefix:
```json
[
  "/xsw/api/health",
  "/xsw/api/categories",
  "/xsw/api/books/{book_id}",
  ...
]
```

## Troubleshooting

### Problem: API returns 404

**Check:**
1. Is router included? `grep "include_router" main_optimized.py`
2. Is route defined before inclusion? Check line numbers
3. Is route using `@api_router` not `@app`?
4. Is there a StaticFiles mount at `/`?

**Solution:**
- Move `include_router()` to end of file
- Change `@app` to `@api_router` for API routes
- Remove root-level StaticFiles mount

### Problem: Static assets return 404

**Check:**
1. Are mounts at specific paths (`/assets`, `/icons`)?
2. Do files exist in the mounted directories?
3. Are routes blocking the mount paths?

**Solution:**
- Use specific mount paths, not `/`
- Check file paths in Docker container
- Ensure routes don't overlap with static paths

### Problem: SPA routes return 404

**Check:**
1. Is SPA fallback middleware present?
2. Does it check for API paths first?
3. Does index.html exist?

**Solution:**
- Add middleware after all routes/mounts
- Exclude API paths in middleware
- Verify SPA build output

## Related Documentation

- [ROUTING_FIX.md](ROUTING_FIX.md) - Detailed explanation of the fix
- [CLAUDE.md](../CLAUDE.md) - Project overview and patterns
- [main_optimized.py](../main_optimized.py) - Main application file

---

**Last Updated**: February 1, 2026
