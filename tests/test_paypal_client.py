"""
ApexMarket Test Suite: Shared PayPal Client
Asserts OAuth token caching and refresh, PayPal-Request-Id headers, error parsing,
and that network errors are raised unchanged. PayPal is mocked with httpx.MockTransport.
"""

import httpx
import pytest

from app.config import Settings
from app.services.paypal_client import PayPalClient, PayPalError, clear_token_cache

pytestmark = pytest.mark.asyncio

BASE = "https://api-m.sandbox.paypal.com"


def sandbox_settings() -> Settings:
    return Settings(PAYPAL_BASE_URL=BASE, PAYPAL_CLIENT_ID="test-id", PAYPAL_CLIENT_SECRET="test-secret")


@pytest.fixture(autouse=True)
def fresh_token_cache():
    clear_token_cache()
    yield
    clear_token_cache()


class FakePayPal:
    """Records requests and answers token calls with numbered tokens."""

    def __init__(self, expires_in: int = 32400, api_responses=None):
        self.expires_in = expires_in
        self.api_responses = list(api_responses or [])
        self.token_calls = 0
        self.api_requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            self.token_calls += 1
            return httpx.Response(200, json={"access_token": f"token-{self.token_calls}", "expires_in": self.expires_in})
        self.api_requests.append(request)
        if self.api_responses:
            return self.api_responses.pop(0)
        return httpx.Response(200, json={"ok": True})


async def test_token_is_cached_across_client_instances():
    fake = FakePayPal()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        for _ in range(3):
            await PayPalClient(sandbox_settings(), http).request("GET", "/v1/ping")

    assert fake.token_calls == 1
    assert all(r.headers["Authorization"] == "Bearer token-1" for r in fake.api_requests)


async def test_token_close_to_expiry_is_refetched():
    fake = FakePayPal(expires_in=30)  # inside the 60s safety margin
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        client = PayPalClient(sandbox_settings(), http)
        await client.request("GET", "/v1/ping")
        await client.request("GET", "/v1/ping")

    assert fake.token_calls == 2


async def test_request_sends_request_id_and_returns_json():
    fake = FakePayPal(api_responses=[httpx.Response(201, json={"id": "ORDER-1"})])
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        body = await PayPalClient(sandbox_settings(), http).request(
            "POST", "/v2/checkout/orders", json={"intent": "CAPTURE"}, request_id="topup-123"
        )

    assert body == {"id": "ORDER-1"}
    assert fake.api_requests[0].headers["PayPal-Request-Id"] == "topup-123"
    assert fake.api_requests[0].url == f"{BASE}/v2/checkout/orders"


async def test_request_without_request_id_omits_header():
    fake = FakePayPal()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        await PayPalClient(sandbox_settings(), http).request("GET", "/v1/ping")

    assert "PayPal-Request-Id" not in fake.api_requests[0].headers


async def test_unauthorized_response_refreshes_token_and_retries_once():
    fake = FakePayPal(api_responses=[httpx.Response(401, json={"error": "invalid_token"}), httpx.Response(200, json={"ok": 1})])
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        body = await PayPalClient(sandbox_settings(), http).request("GET", "/v1/ping", request_id="same-id")

    assert body == {"ok": 1}
    assert fake.token_calls == 2
    assert [r.headers["Authorization"] for r in fake.api_requests] == ["Bearer token-1", "Bearer token-2"]
    assert all(r.headers["PayPal-Request-Id"] == "same-id" for r in fake.api_requests)


async def test_error_response_raises_paypal_error_with_details():
    error_body = {"name": "UNPROCESSABLE_ENTITY", "message": "The requested action could not be performed.", "debug_id": "abc123"}
    fake = FakePayPal(api_responses=[httpx.Response(422, json=error_body)])
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        with pytest.raises(PayPalError) as exc_info:
            await PayPalClient(sandbox_settings(), http).request("POST", "/v2/checkout/orders/X/capture")

    assert exc_info.value.status_code == 422
    assert exc_info.value.name == "UNPROCESSABLE_ENTITY"
    assert exc_info.value.debug_id == "abc123"


async def test_network_error_is_raised_unchanged():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 32400})
        raise httpx.ReadTimeout("no response", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(httpx.ReadTimeout):
            await PayPalClient(sandbox_settings(), http).request("POST", "/v1/anything", request_id="r1")
