"""
ApexMarket: Shared Async PayPal REST Client
Caches OAuth access tokens across requests so each API call does not pay for a
fresh token exchange.
"""

import asyncio
import time
from typing import Dict, Tuple

import httpx

from app.config import Settings

# Refresh tokens this many seconds before PayPal says they expire.
TOKEN_EXPIRY_MARGIN_S = 60

# (base_url, client_id) -> (access_token, expires_at_monotonic)
_token_cache: Dict[Tuple[str, str], Tuple[str, float]] = {}
_token_lock = asyncio.Lock()


def clear_token_cache() -> None:
    """Forgets all cached access tokens (used by tests and after credential changes)."""
    _token_cache.clear()


class PayPalClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.settings = settings
        self.http = http
        self.base_url = settings.PAYPAL_BASE_URL.rstrip("/")

    @property
    def _cache_key(self) -> Tuple[str, str]:
        return self.base_url, self.settings.PAYPAL_CLIENT_ID

    async def access_token(self, force_refresh: bool = False) -> str:
        """Returns a cached OAuth token, fetching a new one when missing or about to expire."""
        async with _token_lock:
            cached = _token_cache.get(self._cache_key)
            if cached and not force_refresh and time.monotonic() < cached[1]:
                return cached[0]

            response = await self.http.post(
                f"{self.base_url}/v1/oauth2/token",
                auth=(self.settings.PAYPAL_CLIENT_ID, self.settings.PAYPAL_CLIENT_SECRET),
                data={"grant_type": "client_credentials"},
            )
            response.raise_for_status()
            data = response.json()
            lifetime_s = max(0, int(data.get("expires_in", 0)) - TOKEN_EXPIRY_MARGIN_S)
            _token_cache[self._cache_key] = (data["access_token"], time.monotonic() + lifetime_s)
            return data["access_token"]
