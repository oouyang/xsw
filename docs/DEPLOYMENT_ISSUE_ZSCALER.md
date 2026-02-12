# Deployment Issue: Zscaler Blocking Access

## Problem

The deployed backend at `http://bolezk03:8000/xsw/api/categories` returns empty results because the container is behind a **Zscaler corporate proxy** that blocks access to `m.xsw.tw`.

## Evidence

1. **Local container works fine:**
   - Direct access to `https://m.xsw.tw/` succeeds
   - HTML contains category links (`fenlei1_1.html`, etc.)
   - Parser finds 7 categories

2. **Deployed container fails:**
   - Access to `https://m.xsw.tw/` redirects to Zscaler auth page
   - HTML is Zscaler authentication form (16KB instead of 37KB)
   - Parser finds 0 categories

3. **Zscaler Authentication Page:**

```html
<!DOCTYPE html><html><head>
<title>Welcome To Zscaler Directory Authentication</title>
...
Please wait a moment while we launch our security service.
...
</html>
```

## Root Cause

The deployed container's network traffic goes through a corporate proxy (`proxy-web.micron.com:80`) which then routes through Zscaler. Zscaler requires authentication for external websites like `m.xsw.tw`.

## Solutions

### Option 1: Add Proxy Bypass for m.xsw.tw (Recommended)

Add `m.xsw.tw` to the `NO_PROXY` environment variable:

```bash
# In docker-compose.yml on bolezk03:
services:
  xsw:
    environment:
      - NO_PROXY=.micron.com,localhost,micron.com,.micron.com,vpce.amazonaws.com,.vpce.amazonaws.com,m.xsw.tw,xsw.tw
```

### Option 2: Configure Zscaler Authentication

If proxy bypass isn't allowed, configure the container to authenticate with Zscaler:

```bash
# Add to docker-compose.yml:
services:
  xsw:
    environment:
      - ZSCALER_USER=your_username
      - ZSCALER_PASS=your_password
```

Then update `main_optimized.py` to use authenticated sessions.

### Option 3: Use VPN or Direct Network

Deploy the container on a network that has direct internet access without going through Zscaler.

### Option 4: Use a Proxy Service

Set up an intermediate proxy service that:

1. Runs outside Zscaler (on a network with direct access)
2. Fetches content from `m.xsw.tw`
3. Provides it to your container

## Recommended Fix

**Add to `/opt/nginx/docker-compose.yml` on bolezk03:**

```yaml
services:
  xsw:
    image: hpctw-docker-dev-local.boartifactory.micron.com/xsw:latest
    container_name: nginx-xsw-1
    restart: unless-stopped
    ports:
      - '8000:8000'
    volumes:
      - ./data:/app/data
    environment:
      - BASE_URL=https://m.xsw.tw
      - DB_PATH=/app/data/xsw_cache.db
      # Add these lines:
      - NO_PROXY=.micron.com,localhost,micron.com,.micron.com,vpce.amazonaws.com,.vpce.amazonaws.com,m.xsw.tw,*.xsw.tw
      - no_proxy=.micron.com,localhost,micron.com,.micron.com,vpce.amazonaws.com,.vpce.amazonaws.com,m.xsw.tw,*.xsw.tw
```

## Testing the Fix

After updating docker-compose.yml:

```bash
# On bolezk03:
cd /opt/nginx
docker compose down xsw
docker compose up -d xsw

# Wait a few seconds, then test:
curl http://localhost:8000/xsw/api/categories

# Should return:
# [{"id":"1","name":"玄幻小說","url":"..."}...]
```

## Verification

Check the logs to confirm HTML is now correct:

```bash
docker logs --tail 20 nginx-xsw-1

# Should show:
# [API] Fetching categories from https://m.xsw.tw/
# [API] Got HTML, length: 37000+  (NOT 16090)
# [API] Found 14+ fenlei matches in HTML
# [API] Found 7 categories
```

## Current Status

- ❌ Deployed container blocked by Zscaler
- ❌ Returns empty categories array
- ✅ Local container works perfectly
- 📋 Solution identified: Add NO_PROXY configuration

## Next Steps

1. SSH to bolezk03
2. Edit `/opt/nginx/docker-compose.yml`
3. Add `NO_PROXY` environment variables
4. Restart container
5. Test API endpoint

## Alternative: Update .env on Host

If the host already has proxy environment variables, you can also create/update `.env` file:

```bash
# On bolezk03 in /opt/nginx/
cat > .env << 'EOF'
NO_PROXY=.micron.com,localhost,micron.com,.micron.com,vpce.amazonaws.com,.vpce.amazonaws.com,m.xsw.tw,*.xsw.tw
no_proxy=.micron.com,localhost,micron.com,.micron.com,vpce.amazonaws.com,.vpce.amazonaws.com,m.xsw.tw,*.xsw.tw
EOF

docker compose down xsw
docker compose up -d xsw
```

## Summary

The issue is **NOT** with your code - it's a network/proxy configuration issue. The deployed environment has Zscaler blocking external website access. Adding the target domain to `NO_PROXY` will resolve the issue immediately.
