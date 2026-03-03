"""
TDX (Transportation Data eXchange) API Client
Handles authentication and API requests to TDX
"""
import os
import time
import logging
from typing import Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class TDXClient:
    """Client for Taiwan TDX API"""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        auth_url: Optional[str] = None
    ):
        self.client_id = client_id or os.getenv('TDX_CLIENT_ID')
        self.client_secret = client_secret or os.getenv('TDX_CLIENT_SECRET')
        self.base_url = base_url or os.getenv(
            'TDX_BASE_URL',
            'https://tdx.transportdata.tw/api/basic'
        )
        self.auth_url = auth_url or os.getenv(
            'TDX_AUTH_URL',
            'https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token'
        )

        self.access_token = None
        self.token_expires_at = 0

        # Session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Disable SSL verification if behind corporate proxy
        if os.getenv('VERIFY_SSL', 'true').lower() == 'false':
            self.session.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _get_access_token(self) -> str:
        """
        Get OAuth2 access token (with automatic refresh)
        Token is valid for 1 day
        """
        # Return cached token if still valid (with 5min buffer)
        if self.access_token and time.time() < (self.token_expires_at - 300):
            return self.access_token

        logger.info("Fetching new TDX access token")

        response = self.session.post(
            self.auth_url,
            data={
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10
        )
        response.raise_for_status()

        data = response.json()
        self.access_token = data['access_token']
        # expires_in is in seconds (usually 86400 = 1 day)
        self.token_expires_at = time.time() + data.get('expires_in', 86400)

        logger.info(f"TDX token obtained, expires in {data.get('expires_in', 0)}s")
        return self.access_token

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Make authenticated request to TDX API
        """
        url = f"{self.base_url}{endpoint}"

        # Check if using proxy (proxy handles auth)
        is_proxy = 'tdx-proxy' in self.base_url.lower()

        if is_proxy:
            # Proxy handles authentication
            headers = {'Accept': 'application/json'}
        else:
            # Direct TDX API requires OAuth2 token
            token = self._get_access_token()
            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json'
            }

        logger.debug(f"TDX request: {endpoint} {params}")

        response = self.session.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        return response.json()

    # ===== Bus Endpoints =====

    def get_estimated_arrival(self, city: str, route_name: str) -> list:
        """
        Get estimated arrival times for a route

        Args:
            city: City name (e.g., "Taoyuan", "Taipei")
            route_name: Route name (e.g., "709")

        Returns:
            List of arrival estimates
        """
        endpoint = f"/v2/Bus/EstimatedTimeOfArrival/City/{city}/{route_name}"
        return self._request(endpoint, params={'$format': 'JSON'})

    def get_bus_stops(self, city: str, route_name: str) -> list:
        """
        Get stops for a route
        """
        endpoint = f"/v2/Bus/Stop/City/{city}/{route_name}"
        return self._request(endpoint, params={'$format': 'JSON'})

    def get_bus_route_shape(self, city: str, route_name: str) -> list:
        """
        Get route geometry (path)
        """
        endpoint = f"/v2/Bus/Shape/City/{city}/{route_name}"
        return self._request(endpoint, params={'$format': 'JSON'})

    def get_bus_realtime_position(self, city: str, route_name: str) -> list:
        """
        Get real-time bus positions
        """
        endpoint = f"/v2/Bus/RealTimeByFrequency/City/{city}/{route_name}"
        return self._request(endpoint, params={'$format': 'JSON'})

    def get_routes(self, city: str) -> list:
        """
        Get all routes in a city
        """
        endpoint = f"/v2/Bus/Route/City/{city}"
        return self._request(endpoint, params={'$format': 'JSON'})

    def get_route_detail(self, city: str, route_name: str) -> list:
        """
        Get route detail including sub-routes
        """
        endpoint = f"/v2/Bus/Route/City/{city}/{route_name}"
        return self._request(endpoint, params={'$format': 'JSON'})

    def get_route_stops_of_route(self, city: str, route_name: str) -> list:
        """
        Get stops with sequence for a route (StopOfRoute)
        Includes Direction and StopSequence
        """
        endpoint = f"/v2/Bus/StopOfRoute/City/{city}/{route_name}"
        return self._request(endpoint, params={'$format': 'JSON'})


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    client = TDXClient()

    # Test: Get route 709 arrival times in Taoyuan
    try:
        arrivals = client.get_estimated_arrival("Taoyuan", "709")
        print(f"Found {len(arrivals)} arrival estimates")

        if arrivals:
            first = arrivals[0]
            print(f"Sample: {first.get('StopName', {}).get('Zh_tw')} - {first.get('EstimateTime')}s")
    except Exception as e:
        logger.error(f"TDX API error: {e}")
