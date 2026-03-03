# DDoS Protection - Quick Integration Guide

## Step-by-Step Integration

### Step 1: Update .env

Add these configuration options:

```bash
# DDoS Protection
DDOS_PROTECTION_ENABLED=true
DDOS_MAX_REQUESTS_PER_IP=100
DDOS_TIME_WINDOW=60
DDOS_BLOCK_DURATION=3600
DDOS_MAX_SUSPICIOUS_SCORE=10
```

### Step 2: Update main_optimized.py

Add imports at the top (around line 60):

```python
from bot_protection import DDoSProtection
```

Add configuration section (around line 100):

```python
# DDoS Protection configuration
DDOS_PROTECTION_ENABLED = os.getenv("DDOS_PROTECTION_ENABLED", "true").lower() == "true"
DDOS_MAX_REQUESTS_PER_IP = int(os.getenv("DDOS_MAX_REQUESTS_PER_IP", "100"))
DDOS_TIME_WINDOW = int(os.getenv("DDOS_TIME_WINDOW", "60"))
DDOS_BLOCK_DURATION = int(os.getenv("DDOS_BLOCK_DURATION", "3600"))
DDOS_MAX_SUSPICIOUS_SCORE = int(os.getenv("DDOS_MAX_SUSPICIOUS_SCORE", "10"))
```

Initialize DDoS protection (around line 450, after RateLimiter):

```python
# Initialize DDoS protection
ddos_protection = None
if DDOS_PROTECTION_ENABLED:
    ddos_protection = DDoSProtection(
        max_requests_per_ip=DDOS_MAX_REQUESTS_PER_IP,
        time_window=DDOS_TIME_WINDOW,
        block_duration=DDOS_BLOCK_DURATION,
        max_suspicious_score=DDOS_MAX_SUSPICIOUS_SCORE
    )
    print(f"[INIT] DDoS Protection enabled")
```

Add middleware class (around line 480, after RateLimitMiddleware):

```python
class BotProtectionMiddleware(BaseHTTPMiddleware):
    """Middleware for bot and DDoS protection"""

    async def dispatch(self, request: Request, call_next):
        if not DDOS_PROTECTION_ENABLED or ddos_protection is None:
            return await call_next(request)

        # Extract client IP (support Cloudflare and proxies)
        client_ip = (
            request.headers.get("cf-connecting-ip") or
            request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
            request.headers.get("x-real-ip") or
            (request.client.host if request.client else "unknown")
        )

        # Get request details
        path = request.url.path
        user_agent = request.headers.get("user-agent", "")
        method = request.method

        # Check if request is allowed
        allowed, reason, delay = ddos_protection.check_request(
            ip=client_ip,
            path=path,
            user_agent=user_agent,
            method=method
        )

        if not allowed:
            print(f"[BotProtection] Blocked {client_ip}: {reason}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": reason,
                    "retry_after": delay
                },
                headers={
                    "Retry-After": str(delay) if delay > 0 else "3600"
                }
            )

        # Apply progressive delay if needed
        if delay > 0:
            print(f"[BotProtection] Throttling {client_ip}: {delay}s delay")
            await asyncio.sleep(delay)

        # Process request
        try:
            response = await call_next(request)

            # Track failed requests for reputation
            if response.status_code >= 400:
                ddos_protection.mark_failed_request(client_ip, response.status_code)

            return response

        except Exception as e:
            # Track errors
            ddos_protection.mark_failed_request(client_ip, 500)
            raise
```

Register middleware (add after RateLimitMiddleware registration):

```python
# Add bot protection middleware
if DDOS_PROTECTION_ENABLED:
    app.add_middleware(BotProtectionMiddleware)
```

### Step 3: Add Admin API Endpoints

Add these endpoints to your API router (around line 1700):

```python
# ======================
# DDoS Protection Admin
# ======================

@api_router.get("/admin/ddos/stats")
def get_ddos_stats(auth: TokenPayload = Depends(require_admin_auth)):
    """Get DDoS protection statistics."""
    if not DDOS_PROTECTION_ENABLED or ddos_protection is None:
        return {"enabled": False}

    return {
        "enabled": True,
        **ddos_protection.get_stats()
    }


@api_router.get("/admin/ddos/client/{ip}")
def get_ddos_client_info(
    ip: str,
    auth: TokenPayload = Depends(require_admin_auth)
):
    """Get detailed information about a specific client."""
    if not DDOS_PROTECTION_ENABLED or ddos_protection is None:
        raise HTTPException(status_code=501, detail="DDoS protection not enabled")

    info = ddos_protection.get_client_info(ip)
    if not info:
        raise HTTPException(status_code=404, detail="Client not found")

    return info


@api_router.post("/admin/ddos/block/{ip}")
def block_ddos_ip(
    ip: str,
    permanent: bool = Query(False, description="Permanent block (vs temporary)"),
    auth: TokenPayload = Depends(require_admin_auth)
):
    """Block an IP address."""
    if not DDOS_PROTECTION_ENABLED or ddos_protection is None:
        raise HTTPException(status_code=501, detail="DDoS protection not enabled")

    ddos_protection.block_ip(ip, permanent=permanent)
    return {
        "message": f"IP {ip} blocked",
        "permanent": permanent,
        "duration": "permanent" if permanent else f"{DDOS_BLOCK_DURATION}s"
    }


@api_router.post("/admin/ddos/unblock/{ip}")
def unblock_ddos_ip(
    ip: str,
    auth: TokenPayload = Depends(require_admin_auth)
):
    """Unblock an IP address."""
    if not DDOS_PROTECTION_ENABLED or ddos_protection is None:
        raise HTTPException(status_code=501, detail="DDoS protection not enabled")

    ddos_protection.unblock_ip(ip)
    return {"message": f"IP {ip} unblocked"}
```

### Step 4: Test the Integration

Restart the server:

```bash
# Kill existing process
pkill -f "uvicorn main_optimized:app"

# Restart with new configuration
uvicorn main_optimized:app --host 0.0.0.0 --port 8000 --reload
```

Test endpoints:

```bash
# Test rate limiting
for i in {1..150}; do
  curl -s http://localhost:8000/xsw/api/health -o /dev/null -w "%{http_code}\n"
done

# Test bot detection
curl -A "scrapy/1.0" http://localhost:8000/xsw/api/health

# Check stats (requires admin token)
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:8000/xsw/api/admin/ddos/stats
```

## Quick Reference Commands

### Monitor Protection

```bash
# Get stats
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/xsw/api/admin/ddos/stats | jq

# Check specific IP
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/xsw/api/admin/ddos/client/192.168.1.100" | jq
```

### Block Management

```bash
# Temporarily block IP (1 hour)
curl -X POST -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/xsw/api/admin/ddos/block/192.168.1.100"

# Permanently block IP
curl -X POST -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/xsw/api/admin/ddos/block/192.168.1.100?permanent=true"

# Unblock IP
curl -X POST -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/xsw/api/admin/ddos/unblock/192.168.1.100"
```

### Debug Logs

```bash
# Watch protection logs
tail -f logs/uvicorn.log | grep -i "bot\|blocked\|ddos"

# Count blocked requests
grep "Blocked" logs/uvicorn.log | wc -l

# Top attacking IPs
grep "Blocked" logs/uvicorn.log | \
  awk '{print $(NF-1)}' | sort | uniq -c | sort -rn | head -10
```

## Configuration Tuning

### Strict Mode (High Security)

For high-security environments:

```bash
DDOS_PROTECTION_ENABLED=true
DDOS_MAX_REQUESTS_PER_IP=50        # Lower limit
DDOS_TIME_WINDOW=60
DDOS_BLOCK_DURATION=7200           # 2 hours
DDOS_MAX_SUSPICIOUS_SCORE=5        # More sensitive
```

### Lenient Mode (Development)

For development/testing:

```bash
DDOS_PROTECTION_ENABLED=true
DDOS_MAX_REQUESTS_PER_IP=500       # Higher limit
DDOS_TIME_WINDOW=60
DDOS_BLOCK_DURATION=300            # 5 minutes
DDOS_MAX_SUSPICIOUS_SCORE=20       # Less sensitive
```

### Production Balanced

Recommended for production:

```bash
DDOS_PROTECTION_ENABLED=true
DDOS_MAX_REQUESTS_PER_IP=100       # Balanced
DDOS_TIME_WINDOW=60
DDOS_BLOCK_DURATION=3600           # 1 hour
DDOS_MAX_SUSPICIOUS_SCORE=10       # Moderate
```

## Cloudflare Setup (Optional but Recommended)

### 1. Add Domain to Cloudflare

1. Sign up at cloudflare.com
2. Add your domain
3. Update nameservers

### 2. Enable Security Features

**Security → Settings**:
- ✅ Enable "Bot Fight Mode"
- ✅ Enable "Security Level: Medium/High"
- ✅ Enable "Challenge Passage: 30 minutes"

**Speed → Caching**:
- ✅ Caching Level: Standard
- ✅ Browser Cache TTL: 4 hours

**Rules → Rate Limiting** (Pro plan):
```
Rule: API Protection
- Path: /api/*
- Rate: 100 requests/minute
- Action: Challenge
```

### 3. Get Real Client IP

Your FastAPI code already handles this:

```python
client_ip = request.headers.get("cf-connecting-ip") or \
           request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
           request.client.host
```

## Expected Behavior

### Normal User

```
Request 1:   200 OK (instant)
Request 2:   200 OK (instant)
...
Request 80:  200 OK (1s delay)
...
Request 95:  200 OK (5s delay)
...
Request 101: 429 Too Many Requests (blocked 1 hour)
```

### Bot/Scanner

```
Request 1: 200 OK (suspicious User-Agent detected)
Request 2: 200 OK (suspicious path detected)
Request 3: 429 Too Many Requests (auto-blocked after suspicious score > 10)
```

### Good Bot (Googlebot)

```
Request 1: 200 OK (whitelisted)
Request 2: 200 OK (no limits)
...
```

## Verification Checklist

- [ ] Bot protection file created (`bot_protection.py`)
- [ ] `.env` updated with DDOS_* variables
- [ ] `main_optimized.py` imports added
- [ ] Middleware registered
- [ ] Admin endpoints added
- [ ] Server restarted
- [ ] Rate limiting tested
- [ ] Bot detection tested
- [ ] Stats endpoint working
- [ ] Cloudflare configured (optional)

## Next Steps

1. **Monitor for 24 hours**: Watch stats and logs
2. **Tune thresholds**: Adjust based on traffic patterns
3. **Set up alerts**: Notify on high block rates
4. **Enable Cloudflare**: Add CDN + WAF for extra protection
5. **Document incidents**: Keep track of attacks

---

**Your API is now protected!** 🛡️

See [DDOS_PROTECTION.md](DDOS_PROTECTION.md) for complete documentation.
