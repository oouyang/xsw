"""
Simple in-memory cache for bus API data
Uses TTL-based expiration
"""
import time
import threading
from typing import Optional


class BusCache:
    """Thread-safe TTL cache for bus data"""

    def __init__(self):
        self._cache = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[str]:
        """Get cached value if not expired"""
        with self._lock:
            if key in self._cache:
                value, expires_at = self._cache[key]
                if time.time() < expires_at:
                    return value
                else:
                    # Expired, remove
                    del self._cache[key]
            return None

    def set(self, key: str, value: str, ttl: int = 60):
        """Set cached value with TTL in seconds"""
        with self._lock:
            expires_at = time.time() + ttl
            self._cache[key] = (value, expires_at)

    def delete(self, key: str):
        """Delete cached value"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self):
        """Clear all cached values"""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self):
        """Remove expired entries"""
        with self._lock:
            now = time.time()
            expired_keys = [
                k for k, (_, expires_at) in self._cache.items()
                if now >= expires_at
            ]
            for k in expired_keys:
                del self._cache[k]

    def get_stats(self) -> dict:
        """Get cache statistics"""
        with self._lock:
            self.cleanup_expired()
            return {
                "size": len(self._cache),
                "keys": list(self._cache.keys())
            }
