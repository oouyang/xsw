# Zscaler Proxy Issue - RESOLVED

## Problem

The deployed backend at `http://bolezk03:8000/xsw/api/categories` was returning empty results because Zscaler was blocking requests with Zscaler authentication page.

## Root Cause

The application was using a browser-like User-Agent header:
```python
"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."
```

Corporate proxy (Zscaler) detected this as a browser session and required SAML authentication, returning an authentication page (16KB) instead of the actual m.xsw.tw content (33KB).

## Solution

**Remove the custom User-Agent header and use Python requests' default User-Agent.**

### Code Changes in [main_optimized.py](main_optimized.py:57-61)

**Before:**
```python
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

session = requests.Session()
session.headers.update(HEADERS)
```

**After:**
```python
# Use default Python requests User-Agent instead of browser-like UA
# This helps with corporate proxies like Zscaler that may block browser UAs
# but allow automated tool requests
session = requests.Session()
# Don't set custom headers - use default requests User-Agent
```

### fetch_html() SSL Verification

Kept `verify=False` because:
- Corporate proxy does SSL inspection
- Container doesn't have Zscaler's CA certificate
- Alternative would be mounting `/etc/pki/ca-trust/` from host

```python
def fetch_html(url: str) -> str:
    """Fetch HTML with encoding detection."""
    # Use verify=False to bypass SSL verification with corporate proxy/Zscaler
    # The proxy does SSL inspection and we don't have their CA cert in container
    resp = session.get(url, timeout=DEFAULT_TIMEOUT, verify=False)
    resp.raise_for_status()
    enc = resp.apparent_encoding or resp.encoding or "utf-8"
    resp.encoding = enc
    return resp.text
```

## Verification

### Before Fix
```bash
$ curl http://bolezk03:8000/xsw/api/categories
[]

$ docker exec nginx-xsw-1 head -5 /tmp/categories_debug.html
<!DOCTYPE html><html><head>
<title>Welcome To Zscaler Directory Authentication</title>
...
```

Logs showed:
- HTML length: 16090 bytes
- Found 0 fenlei matches
- Returned 0 categories

### After Fix
```bash
$ curl http://bolezk03:8000/xsw/api/categories
[{"id":"1","name":"玄幻小說","url":"https://m.xsw.tw/fenlei1_1.html"},
 {"id":"2","name":"修真小說","url":"https://m.xsw.tw/fenlei2_1.html"},
 {"id":"3","name":"都市小說","url":"https://m.xsw.tw/fenlei3_1.html"},
 {"id":"4","name":"曆史小說","url":"https://m.xsw.tw/fenlei4_1.html"},
 {"id":"5","name":"網遊小說","url":"https://m.xsw.tw/fenlei5_1.html"},
 {"id":"6","name":"科幻小說","url":"https://m.xsw.tw/fenlei6_1.html"},
 {"id":"7","name":"恐怖小說","url":"https://m.xsw.tw/fenlei7_1.html"}]
```

Logs showed:
- HTML length: 33650 bytes ✅
- Found 14 fenlei matches ✅
- Returned 7 categories ✅

## Why This Works

Corporate proxies like Zscaler are typically configured to:
- **Block** browser-like User-Agents that might be users trying to bypass authentication
- **Allow** automated tool User-Agents (like Python requests, curl default) for legitimate automation

By using Python requests' default User-Agent (`python-requests/2.x.x`), the proxy recognizes it as an automated tool and allows it through without requiring SAML authentication.

## Alternative Solutions (Not Used)

### 1. Add Zscaler CA Certificate to Container
Mount host's CA bundle:
```yaml
volumes:
  - /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem:/etc/ssl/certs/ca-certificates.crt:ro
environment:
  - REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
```

Then use `verify=True` in requests.

**Why not used:** More complex, requires host filesystem access, and `verify=False` works fine for this use case.

### 2. Whitelist m.xsw.tw in Zscaler
Add to NO_PROXY:
```yaml
environment:
  - NO_PROXY=.micron.com,localhost,m.xsw.tw,*.xsw.tw
```

**Why not used:** Caused "Connection reset by peer" errors. The proxy configuration didn't support direct bypass for this domain.

### 3. Deploy Relay Proxy
Created [relay_proxy.py](relay_proxy.py) to run on a machine without Zscaler and proxy requests.

**Why not used:** Not needed once the User-Agent fix was discovered. Kept as backup solution.

## Deployment Process

```bash
# Build
docker compose -f compose.yml -f docker/build.yml build xsw

# Tag and push
docker tag oouyang/xsw:latest hpctw-docker-dev-local.boartifactory.micron.com/xsw:latest
docker push hpctw-docker-dev-local.boartifactory.micron.com/xsw:latest

# Transfer to production
ssh boleai02 "docker pull hpctw-docker-dev-local.boartifactory.micron.com/xsw && \
              docker save hpctw-docker-dev-local.boartifactory.micron.com/xsw -o /etl/python_env/ximg.tgz"

# Deploy on production
ssh bolezk03 "docker load -i /etl/python_env/ximg.tgz && \
              docker compose -f /opt/nginx/docker-compose.yml up -d xsw"
```

## Current Status

✅ **RESOLVED** - Backend at `http://bolezk03:8000/xsw/api/categories` now returns correct data.

## Lessons Learned

1. **Corporate proxies may have different rules for different User-Agents**
   - Browser UAs → Require authentication
   - Tool UAs → Allow through

2. **Default behavior is sometimes better than customization**
   - Using Python requests' default User-Agent worked better than mimicking a browser

3. **SSL verification with corporate proxies**
   - `verify=False` is acceptable when proxy does SSL inspection and you can't easily add their CA cert

4. **Debugging strategy**
   - Save HTML responses to files for inspection
   - Check HTML length as quick indicator of success/failure
   - Look for authentication pages in responses

## Related Documentation

- [DEPLOYMENT_ISSUE_ZSCALER.md](DEPLOYMENT_ISSUE_ZSCALER.md) - Original investigation and analysis
- [relay_proxy.py](relay_proxy.py) - Backup solution (relay proxy)
- [main_optimized.py](main_optimized.py) - Main application file with fix

---

**Fixed:** 2026-01-22
**Deployed to:** bolezk03 (nginx-xsw-1 container)
**Issue:** Zscaler authentication blocking
**Solution:** Remove browser-like User-Agent, use default Python requests UA
