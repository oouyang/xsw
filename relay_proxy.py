#!/usr/bin/env python3
"""
Simple HTTP relay proxy to bypass Zscaler for m.xsw.tw

This can be deployed on a machine with direct internet access (not behind Zscaler)
and act as a relay for the main application.

Usage:
    python relay_proxy.py --port 8080

Then configure main app to use:
    BASE_URL=http://relay-host:8080/proxy
"""
import argparse
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
import requests
import uvicorn

app = FastAPI(title="XSW Relay Proxy")

# Target site
TARGET_BASE = "https://m.xsw.tw"

# Session with proper headers
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
})


@app.get("/proxy/")
@app.get("/proxy/{path:path}")
async def proxy_request(path: str = ""):
    """
    Proxy requests to m.xsw.tw

    Examples:
        GET /proxy/ -> https://m.xsw.tw/
        GET /proxy/123/ -> https://m.xsw.tw/123/
        GET /proxy/123/456.html -> https://m.xsw.tw/123/456.html
    """
    try:
        # Build target URL
        if path:
            target_url = f"{TARGET_BASE}/{path}"
        else:
            target_url = f"{TARGET_BASE}/"

        print(f"[Relay] Fetching: {target_url}")

        # Fetch from target
        resp = session.get(target_url, timeout=30)
        resp.raise_for_status()

        # Detect encoding
        enc = resp.apparent_encoding or resp.encoding or "utf-8"
        resp.encoding = enc

        # Return response with proper content type
        content_type = resp.headers.get("Content-Type", "text/html; charset=utf-8")

        print(f"[Relay] Success: {len(resp.text)} chars, encoding={enc}")

        return Response(
            content=resp.text,
            media_type=content_type,
            headers={
                "X-Relay-Target": target_url,
                "X-Relay-Encoding": enc,
            }
        )

    except requests.RequestException as e:
        print(f"[Relay] Error: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch from target: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "target": TARGET_BASE}


def main():
    parser = argparse.ArgumentParser(description="XSW Relay Proxy")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    args = parser.parse_args()

    print(f"Starting XSW Relay Proxy on {args.host}:{args.port}")
    print(f"Proxying requests to: {TARGET_BASE}")
    print("\nUsage in main app:")
    print(f"  BASE_URL=http://{args.host}:{args.port}/proxy")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
