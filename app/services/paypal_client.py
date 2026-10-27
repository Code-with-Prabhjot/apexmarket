"""
ApexMarket: Shared Async PayPal REST Client
Caches OAuth access tokens across requests so each API call does not pay for a
fresh token exchange, and sends PayPal-Request-Id so retried calls are idempotent.
Network errors (timeouts, dropped connections) are raised unchanged: the outcome is
unknown, so callers retry with the same request id instead of assuming failure.
"""

import time
from typing import Any, Dict, Optional, Tuple

import httpx

from app.config import Settings

# Refresh tokens this many seconds before PayPal says they expire.
TOKEN_EXPIRY_MARGIN_S = 60

# (base_url, client_id) -> (access_token, expires_at_monotonic)
# No lock: two concurrent refreshes are harmless, and a module-level asyncio.Lock
# would bind to the first event loop that uses it.
_token_cache: Dict[Tuple[str, str], Tuple[str, float]] = {}


def clear_token_cache() -> None:
    """Forgets all cached access tokens (used by tests and after credential changes)."""
    _token_cache.clear()


class PayPalError(Exception):
    """A definite error response from PayPal (HTTP 4xx/5xx with a body we could read)."""

    def __init__(self, status_code: int, name: str, message: str, debug_id: Optional[str], body: Dict[str, Any]):
        super().__init__(f"PayPal {status_code} {name}: {message} (debug_id={debug_id})")
        self.status_code = status_code
        self.name = name
        self.debug_id = debug_id
        self.body = body

    @classmethod
    def from_response(cls, response: httpx.Response) -> "PayPalError":
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return cls(
            status_code=response.status_code,
            name=str(body.get("name") or body.get("error") or "UNKNOWN_ERROR"),
            message=str(body.get("message") or body.get("error_description") or response.reason_phrase),
            debug_id=body.get("debug_id"),
            body=body,
        )


_shared_client: Optional[httpx.AsyncClient] = None


def get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=20.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
    return _shared_client


async def close_shared_client() -> None:
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None


class PayPalClient:
    def __init__(self, settings: Settings, http: Optional[httpx.AsyncClient] = None):
        self.settings = settings
        self.http = http or get_shared_client()
        self.base_url = settings.PAYPAL_BASE_URL.rstrip("/")

    @property
    def _cache_key(self) -> Tuple[str, str]:
        return self.base_url, self.settings.PAYPAL_CLIENT_ID

    async def access_token(self, force_refresh: bool = False) -> str:
        """Returns a cached OAuth token, fetching a new one when missing or about to expire."""
        cached = _token_cache.get(self._cache_key)
        if cached and not force_refresh and time.monotonic() < cached[1]:
            return cached[0]

        response = await self.http.post(
            f"{self.base_url}/v1/oauth2/token",
            auth=(self.settings.PAYPAL_CLIENT_ID, self.settings.PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
        )
        if response.status_code >= 400:
            raise PayPalError.from_response(response)
        data = response.json()
        lifetime_s = max(0, int(data.get("expires_in", 0)) - TOKEN_EXPIRY_MARGIN_S)
        _token_cache[self._cache_key] = (data["access_token"], time.monotonic() + lifetime_s)
        return data["access_token"]

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calls a PayPal REST endpoint and returns the JSON body.
        request_id is sent as PayPal-Request-Id; repeating a call with the same id returns
        the original result instead of performing the action twice. An expired token is
        refreshed and the call retried once.
        """
        response = None
        for force_refresh in (False, True):
            headers = {
                "Authorization": f"Bearer {await self.access_token(force_refresh=force_refresh)}",
                "Content-Type": "application/json",
            }
            if request_id:
                headers["PayPal-Request-Id"] = request_id
            response = await self.http.request(
                method, f"{self.base_url}{path}", json=json, params=params, headers=headers
            )
            if response.status_code != 401:
                break

        if response.status_code >= 400:
            raise PayPalError.from_response(response)
        return response.json() if response.content else {}
