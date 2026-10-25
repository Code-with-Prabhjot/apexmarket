"""
ApexMarket Test Suite: Provider API Key Routing
Asserts provider keys are attached only to endpoints with exactly the configured
provider's origin, never to lookalike hosts, other schemes, or other ports.
"""

import pytest

from app.config import Settings
from app.services.orchestration_service import provider_api_key

CONFIG = Settings(
    NEBIUS_BASE_URL="https://api.tokenfactory.nebius.com/v1",
    NEBIUS_API_KEY="nebius-key",
    SECONDARY_BASE_URL="https://openrouter.ai/api/v1",
    SECONDARY_API_KEY="secondary-key",
)


@pytest.mark.parametrize("endpoint,expected", [
    ("https://api.tokenfactory.nebius.com/v1", "nebius-key"),
    ("https://API.TokenFactory.Nebius.com/v1/", "nebius-key"),
    ("https://openrouter.ai/api/v1", "secondary-key"),
    ("https://api.tokenfactory.nebius.com.attacker.io/v1", None),
    ("https://attacker.io/api.tokenfactory.nebius.com/v1", None),
    ("http://api.tokenfactory.nebius.com/v1", None),
    ("https://api.tokenfactory.nebius.com:8443/v1", None),
    ("http://localhost:8001/v1", None),
])
def test_keys_only_go_to_the_configured_provider_origin(endpoint, expected):
    assert provider_api_key(endpoint, CONFIG) == expected


def test_no_key_configured_means_no_key_sent():
    config = Settings(NEBIUS_BASE_URL="https://api.tokenfactory.nebius.com/v1", NEBIUS_API_KEY="")
    assert provider_api_key("https://api.tokenfactory.nebius.com/v1", config) is None
