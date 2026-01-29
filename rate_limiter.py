# rate_limiter.py
"""
Progressive rate limiter with sliding window.

Tracks requests per client IP and applies progressive delays:
- 0-50 requests/min: no delay
- 51-100 requests/min: 1 second delay
- 101-200 requests/min: 10 seconds delay
- 201-500 requests/min: 60 seconds delay
- 500+ requests/min: 300 seconds delay
"""

import time
import threading
from typing import Dict, List, Set, Union
from ipaddress import ip_address, ip_network, IPv4Address, IPv6Address, IPv4Network, IPv6Network


class RateLimiter:
    """Progressive rate limiter with sliding window"""

    # Thresholds and delays (requests per minute -> delay in seconds)
    THRESHOLDS = [
        (50, 0.0),      # 0-50: no delay
        (100, 1.0),     # 51-100: 1 second
        (200, 10.0),    # 101-200: 10 seconds
        (500, 60.0),    # 201-500: 60 seconds
        (float('inf'), 300.0)  # 500+: 300 seconds
    ]

    WINDOW_SECONDS = 60.0  # 1-minute sliding window

    def __init__(self, whitelist: List[str]):
        self._request_history: Dict[str, List[float]] = {}
        self._whitelist_ips: Set[str] = set()
        self._whitelist_networks: List[Union[IPv4Network, IPv6Network]] = []
        self._lock = threading.Lock()

        # Parse whitelist
        for entry in whitelist:
            entry = entry.strip()
            if not entry:
                continue
            try:
                # Try parsing as CIDR network
                if '/' in entry:
                    self._whitelist_networks.append(ip_network(entry, strict=False))
                    print(f"[RateLimiter] Added network to whitelist: {entry}")
                else:
                    # Single IP address - validate it
                    ip_address(entry)  # This will raise ValueError if invalid
                    self._whitelist_ips.add(entry)
                    print(f"[RateLimiter] Added IP to whitelist: {entry}")
            except ValueError:
                print(f"[RateLimiter] Invalid whitelist entry: {entry}")

        print(f"[RateLimiter] Initialized with {len(self._whitelist_ips)} IPs and {len(self._whitelist_networks)} networks")

    def _is_whitelisted(self, client_ip: str) -> bool:
        """Check if IP is whitelisted"""
        # Check exact match first (fast path)
        if client_ip in self._whitelist_ips:
            return True

        # Check network ranges
        try:
            ip = ip_address(client_ip)
            for network in self._whitelist_networks:
                if ip in network:
                    return True
        except ValueError:
            # Invalid IP address format
            pass

        return False

    def _clean_old_requests(self, client_ip: str, now: float):
        """Remove requests older than WINDOW_SECONDS"""
        if client_ip not in self._request_history:
            return

        cutoff = now - self.WINDOW_SECONDS
        self._request_history[client_ip] = [
            ts for ts in self._request_history[client_ip]
            if ts > cutoff
        ]

        # Remove empty entries to prevent memory bloat
        if not self._request_history[client_ip]:
            del self._request_history[client_ip]

    def get_delay(self, client_ip: str) -> float:
        """
        Calculate delay for client based on request count in sliding window.
        Returns delay in seconds (0 means no delay).
        """
        # Whitelist bypass
        if self._is_whitelisted(client_ip):
            return 0.0

        now = time.time()

        with self._lock:
            # Clean old requests outside the window
            self._clean_old_requests(client_ip, now)

            # Count requests in current window
            request_count = len(self._request_history.get(client_ip, []))

            # Find appropriate delay based on thresholds
            for threshold, delay in self.THRESHOLDS:
                if request_count < threshold:
                    return delay

            # Fallback (should never reach here due to inf threshold)
            return self.THRESHOLDS[-1][1]

    def record_request(self, client_ip: str):
        """Record a new request from client"""
        now = time.time()

        with self._lock:
            if client_ip not in self._request_history:
                self._request_history[client_ip] = []

            self._request_history[client_ip].append(now)

            # Clean old requests to prevent unbounded memory growth
            self._clean_old_requests(client_ip, now)

    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        with self._lock:
            now = time.time()

            # Clean all old requests first
            for client_ip in list(self._request_history.keys()):
                self._clean_old_requests(client_ip, now)

            return {
                "active_clients": len(self._request_history),
                "total_requests_in_window": sum(
                    len(reqs) for reqs in self._request_history.values()
                ),
                "whitelist_ips": len(self._whitelist_ips),
                "whitelist_networks": len(self._whitelist_networks),
            }
