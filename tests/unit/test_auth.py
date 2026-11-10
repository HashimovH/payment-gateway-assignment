import pytest
from fastapi.testclient import TestClient

from payment_gateway_api.app import app
from payment_gateway_api.auth import API_KEY_PREFIX, generate_api_key, hash_api_key
from payment_gateway_api.dependencies.merchants import get_merchant_repository
from payment_gateway_api.models.merchant import Merchant

VALID_KEY = "sk_test_valid"


class FakeMerchantRepository:
    def __init__(self, *merchants: Merchant) -> None:
        self._by_hash = {m.api_key_hash: m for m in merchants if m.is_active}

    async def get_active_by_api_key_hash(self, api_key_hash: str) -> Merchant | None:
        return self._by_hash.get(api_key_hash)


@pytest.fixture
def client():
    merchants = FakeMerchantRepository(
        Merchant(name="Active", api_key_hash=hash_api_key(VALID_KEY), is_active=True),
        Merchant(name="Disabled", api_key_hash=hash_api_key("sk_test_disabled"), is_active=False),
    )
    app.dependency_overrides[get_merchant_repository] = lambda: merchants
    yield TestClient(app)
    app.dependency_overrides.clear()


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


# --- API keys ----------------------------------------------------------------------


def test_generated_keys_are_prefixed_and_unique():
    keys = {generate_api_key() for _ in range(100)}

    assert len(keys) == 100
    assert all(key.startswith(API_KEY_PREFIX) for key in keys)


def test_hash_is_deterministic_sha256_hex():
    assert hash_api_key("sk_abc") == hash_api_key("sk_abc")
    assert len(hash_api_key("sk_abc")) == 64
    assert hash_api_key("sk_abc") != hash_api_key("sk_abd")


# --- protected endpoints -----------------------------------------------------------

PROTECTED = [("POST", "/payments"), ("GET", "/payments/some-id")]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
@pytest.mark.parametrize(
    "headers",
    [
        {},  # no header
        bearer("sk_test_unknown"),  # unknown key
        bearer("sk_test_disabled"),  # deactivated merchant
        {"Authorization": f"Basic {VALID_KEY}"},  # wrong scheme
        {"Authorization": VALID_KEY},  # no scheme
    ],
)
def test_requests_without_a_valid_key_get_401(client, method, path, headers):
    response = client.request(method, path, headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": "Invalid or missing API key"}


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_valid_key_passes_authentication(client, method, path):
    response = client.request(method, path, headers=bearer(VALID_KEY))

    # Endpoints are still stubs: reaching them is what proves auth passed.
    assert response.status_code == 501


@pytest.mark.parametrize("path", ["/", "/health", "/liveness"])
def test_public_endpoints_need_no_key(client, path):
    assert client.get(path).status_code == 200
