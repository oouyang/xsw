"""
Bot Protection and DDoS Prevention

Multi-layer defense:
1. Bot detection (User-Agent analysis)
2. Request pattern analysis
3. IP reputation tracking
4. Challenge-response mechanism
5. Connection rate limiting
6. Suspicious behavior detection
"""

import time
import re
import threading
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ClientReputation:
    """Track client behavior and reputation"""
    ip: str
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    total_requests: int = 0
    failed_requests: int = 0
    suspicious_count: int = 0
    blocked_until: Optional[float] = None
    user_agents: Set[str] = field(default_factory=set)
    paths: List[str] = field(default_factory=list)

    def update(self):
        """Update timestamps and counters"""
        self.last_seen = time.time()
        self.total_requests += 1

    def mark_suspicious(self):
        """Mark suspicious behavior"""
        self.suspicious_count += 1
        self.last_seen = time.time()

    def mark_failed(self):
        """Mark failed request (404, 403, etc)"""
        self.failed_requests += 1
        self.last_seen = time.time()

    def is_blocked(self) -> bool:
        """Check if currently blocked"""
        if self.blocked_until is None:
            return False
        return time.time() < self.blocked_until

    def block(self, duration_seconds: int = 3600):
        """Block client for specified duration"""
        self.blocked_until = time.time() + duration_seconds

    def get_reputation_score(self) -> float:
        """Calculate reputation score (0-100, higher is better)"""
        if self.total_requests == 0:
            return 50.0  # Neutral for new clients

        # Start with 100
        score = 100.0

        # Penalize high failure rate
        failure_rate = self.failed_requests / self.total_requests
        score -= failure_rate * 50

        # Penalize suspicious behavior
        suspicious_rate = self.suspicious_count / self.total_requests
        score -= suspicious_rate * 30

        # Bonus for established clients with good history
        age_hours = (time.time() - self.first_seen) / 3600
        if age_hours > 24 and failure_rate < 0.1:
            score += 10

        return max(0.0, min(100.0, score))


class BotDetector:
    """Detect bot and malicious traffic"""

    # Known bot user agents (bad bots)
    BAD_BOT_PATTERNS = [
        r'(?i)(scrapy|curl|wget|python-requests|go-http-client)',
        r'(?i)(bot|crawler|spider|scraper)',
        r'(?i)(sqlmap|nikto|nmap|masscan)',
        r'(?i)(scanner|penetration|attack)',
    ]

    # Good bots (allow these)
    GOOD_BOT_PATTERNS = [
        r'(?i)googlebot',
        r'(?i)bingbot',
        r'(?i)slackbot',
        r'(?i)twitterbot',
        r'(?i)facebookexternalhit',
    ]

    # Suspicious paths
    SUSPICIOUS_PATHS = [
        r'/admin',
        r'/wp-admin',
        r'\.php$',
        r'\.asp$',
        r'/phpmyadmin',
        r'/\.env',
        r'/\.git',
        r'/api/v[0-9]+',  # Version scanning
        r'/(etc|passwd|shadow)',
        r'\.\./\.\.',  # Path traversal
    ]

    def __init__(self):
        self._bad_bot_regex = [re.compile(p) for p in self.BAD_BOT_PATTERNS]
        self._good_bot_regex = [re.compile(p) for p in self.GOOD_BOT_PATTERNS]
        self._suspicious_path_regex = [re.compile(p) for p in self.SUSPICIOUS_PATHS]

    def is_bad_bot(self, user_agent: str) -> bool:
        """Check if user agent is a known bad bot"""
        if not user_agent:
            return True  # No user agent is suspicious

        # Check good bots first (whitelist)
        for pattern in self._good_bot_regex:
            if pattern.search(user_agent):
                return False

        # Check bad bots
        for pattern in self._bad_bot_regex:
            if pattern.search(user_agent):
                return True

        return False

    def is_suspicious_path(self, path: str) -> bool:
        """Check if path is suspicious"""
        for pattern in self._suspicious_path_regex:
            if pattern.search(path):
                return True
        return False

    def analyze_user_agent(self, user_agent: str) -> Tuple[bool, str]:
        """
        Analyze user agent for bot characteristics

        Returns:
            (is_suspicious, reason)
        """
        if not user_agent or len(user_agent) < 10:
            return True, "Missing or too short user agent"

        if self.is_bad_bot(user_agent):
            return True, "Known bad bot pattern"

        # Check for common browser patterns
        browser_indicators = ['Mozilla', 'Chrome', 'Safari', 'Firefox', 'Edge']
        has_browser = any(ind in user_agent for ind in browser_indicators)

        if not has_browser:
            return True, "No browser indicators"

        return False, "OK"


class DDoSProtection:
    """
    Multi-layer DDoS protection

    Features:
    - IP reputation tracking
    - Connection rate limiting
    - Automatic IP blocking
    - Bot detection
    - Pattern analysis
    """

    def __init__(
        self,
        max_requests_per_ip: int = 100,
        time_window: int = 60,
        block_duration: int = 3600,
        max_suspicious_score: int = 10
    ):
        self.max_requests_per_ip = max_requests_per_ip
        self.time_window = time_window
        self.block_duration = block_duration
        self.max_suspicious_score = max_suspicious_score

        self._clients: Dict[str, ClientReputation] = {}
        self._blocked_ips: Set[str] = set()
        self._request_timestamps: Dict[str, deque] = defaultdict(lambda: deque())
        self._lock = threading.Lock()

        self._bot_detector = BotDetector()

        # Statistics
        self._total_requests = 0
        self._blocked_requests = 0
        self._suspicious_requests = 0

        print("[DDoSProtection] Initialized with:")
        print(f"  Max requests/IP: {max_requests_per_ip} per {time_window}s")
        print(f"  Block duration: {block_duration}s")
        print(f"  Max suspicious score: {max_suspicious_score}")

    def _get_or_create_client(self, ip: str) -> ClientReputation:
        """Get or create client reputation object"""
        if ip not in self._clients:
            self._clients[ip] = ClientReputation(ip=ip)
        return self._clients[ip]

    def _clean_old_timestamps(self, ip: str):
        """Remove timestamps outside the time window"""
        if ip not in self._request_timestamps:
            return

        cutoff = time.time() - self.time_window
        timestamps = self._request_timestamps[ip]

        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        if not timestamps:
            del self._request_timestamps[ip]

    def check_request(
        self,
        ip: str,
        path: str,
        user_agent: Optional[str] = None,
        method: str = "GET"
    ) -> Tuple[bool, str, int]:
        """
        Check if request should be allowed

        Returns:
            (allowed, reason, delay_seconds)
        """
        with self._lock:
            self._total_requests += 1

            # Check if IP is currently blocked
            client = self._get_or_create_client(ip)
            if client.is_blocked():
                self._blocked_requests += 1
                remaining = int(client.blocked_until - time.time())
                return False, f"IP blocked for {remaining}s", 0

            # Check if IP is in permanent blacklist
            if ip in self._blocked_ips:
                self._blocked_requests += 1
                return False, "IP permanently blocked", 0

            # Bot detection
            if user_agent:
                is_suspicious_ua, ua_reason = self._bot_detector.analyze_user_agent(user_agent)
                if is_suspicious_ua:
                    client.mark_suspicious()
                    self._suspicious_requests += 1

                    # Auto-block after too many suspicious requests
                    if client.suspicious_count >= self.max_suspicious_score:
                        client.block(self.block_duration)
                        return False, f"Bot detected: {ua_reason}", 0

                client.user_agents.add(user_agent[:100])  # Limit length

            # Path analysis
            if self._bot_detector.is_suspicious_path(path):
                client.mark_suspicious()
                self._suspicious_requests += 1
                return False, "Suspicious path detected", 0

            # Rate limiting
            self._clean_old_timestamps(ip)
            timestamps = self._request_timestamps[ip]
            timestamps.append(time.time())

            request_count = len(timestamps)

            # Progressive throttling
            if request_count > self.max_requests_per_ip:
                client.mark_suspicious()
                # Auto-block aggressive clients
                client.block(self.block_duration)
                return False, f"Rate limit exceeded ({request_count} req/{self.time_window}s)", 0

            # Progressive delay for high-rate clients
            delay = 0
            if request_count > self.max_requests_per_ip * 0.8:
                delay = 5  # 5s delay for clients near limit
            elif request_count > self.max_requests_per_ip * 0.5:
                delay = 1  # 1s delay for moderate traffic

            # Update client stats
            client.update()
            client.paths.append(path[:100])
            if len(client.paths) > 100:
                client.paths.pop(0)  # Keep last 100

            return True, "OK", delay

    def mark_failed_request(self, ip: str, status_code: int):
        """Mark a failed request (404, 403, 500, etc)"""
        with self._lock:
            client = self._get_or_create_client(ip)
            client.mark_failed()

            # Auto-block clients with too many 404s (path scanning)
            if status_code == 404:
                failure_rate = client.failed_requests / max(client.total_requests, 1)
                if failure_rate > 0.5 and client.total_requests > 20:
                    client.block(self.block_duration)

    def block_ip(self, ip: str, permanent: bool = False):
        """Block an IP address"""
        with self._lock:
            if permanent:
                self._blocked_ips.add(ip)
                print(f"[DDoSProtection] Permanently blocked IP: {ip}")
            else:
                client = self._get_or_create_client(ip)
                client.block(self.block_duration)
                print(f"[DDoSProtection] Temporarily blocked IP: {ip} for {self.block_duration}s")

    def unblock_ip(self, ip: str):
        """Unblock an IP address"""
        with self._lock:
            if ip in self._blocked_ips:
                self._blocked_ips.remove(ip)
            if ip in self._clients:
                self._clients[ip].blocked_until = None
            print(f"[DDoSProtection] Unblocked IP: {ip}")

    def get_stats(self) -> Dict:
        """Get protection statistics"""
        with self._lock:
            now = time.time()

            # Clean up old clients (not seen in last hour)
            cutoff = now - 3600
            old_clients = [ip for ip, client in self._clients.items()
                          if client.last_seen < cutoff and not client.is_blocked()]
            for ip in old_clients:
                del self._clients[ip]
                if ip in self._request_timestamps:
                    del self._request_timestamps[ip]

            # Calculate statistics
            active_clients = len(self._clients)
            blocked_clients = sum(1 for c in self._clients.values() if c.is_blocked())
            suspicious_clients = sum(1 for c in self._clients.values()
                                    if c.suspicious_count > 0)

            # Top offenders
            top_requesters = sorted(
                self._clients.items(),
                key=lambda x: len(self._request_timestamps.get(x[0], [])),
                reverse=True
            )[:10]

            return {
                "total_requests": self._total_requests,
                "blocked_requests": self._blocked_requests,
                "suspicious_requests": self._suspicious_requests,
                "active_clients": active_clients,
                "blocked_clients": blocked_clients,
                "suspicious_clients": suspicious_clients,
                "permanently_blocked": len(self._blocked_ips),
                "top_requesters": [
                    {
                        "ip": ip,
                        "requests": len(self._request_timestamps.get(ip, [])),
                        "reputation": client.get_reputation_score(),
                        "suspicious": client.suspicious_count,
                        "blocked": client.is_blocked()
                    }
                    for ip, client in top_requesters
                ]
            }

    def get_client_info(self, ip: str) -> Optional[Dict]:
        """Get detailed information about a specific client"""
        with self._lock:
            if ip not in self._clients:
                return None

            client = self._clients[ip]
            return {
                "ip": ip,
                "first_seen": datetime.fromtimestamp(client.first_seen).isoformat(),
                "last_seen": datetime.fromtimestamp(client.last_seen).isoformat(),
                "total_requests": client.total_requests,
                "failed_requests": client.failed_requests,
                "suspicious_count": client.suspicious_count,
                "reputation_score": client.get_reputation_score(),
                "is_blocked": client.is_blocked(),
                "blocked_until": datetime.fromtimestamp(client.blocked_until).isoformat()
                                if client.blocked_until else None,
                "user_agents": list(client.user_agents)[:10],
                "recent_paths": client.paths[-20:],
                "current_rate": len(self._request_timestamps.get(ip, []))
            }
