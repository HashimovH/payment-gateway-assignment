"""Integration test setup: the real app, a real Postgres and the bank simulator.

Requires `make test-db-up` (test_db on :5433 + bank_simulator on :8080, with
Mountebank's admin API on :2525 for the extra imposters some tests create).
The app runs in-process behind httpx's ASGITransport, so tests only talk to
it over HTTP; the database is migrated once per session and emptied before
every test.
"""

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from payment_gateway_api.app import app
from payment_gateway_api.auth import generate_api_key, hash_api_key
from payment_gateway_api.clients.bank import BankClient
from payment_gateway_api.config import get_settings
from payment_gateway_api.db import get_engine, get_session_factory
from payment_gateway_api.dependencies.payments import get_bank_client
from payment_gateway_api.models.merchant import Merchant

ROOT = Path(__file__).resolve().parents[2]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://gateway:gateway@localhost:5433/payment_gateway_test",
)
TEST_BANK_URL = os.environ.get("TEST_BANK_URL", "http://localhost:8080")
TEST_MOUNTEBANK_URL = os.environ.get("TEST_MOUNTEBANK_URL", "http://localhost:2525")

CreateMerchant = Callable[[str], Awaitable[str]]


def _clear_cached_singletons() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def test_environment():
    """Point the app at the test database and bank for the whole session."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENVIRONMENT", "test")
        mp.setenv("DATABASE_URL", TEST_DATABASE_URL)
        mp.setenv("BANK_URL", TEST_BANK_URL)
        _clear_cached_singletons()
        yield
    _clear_cached_singletons()


@pytest.fixture(scope="session")
def migrated_db(test_environment) -> None:
    """Bring the test database schema to head, exactly as production does."""
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    try:
        command.upgrade(config, "head")
    except OSError as exc:  # connection refused, DNS failure, ...
        pytest.exit(
            f"Test database is unreachable ({exc}). Start it with `make test-db-up`.",
            returncode=1,
        )


@pytest.fixture
async def client(migrated_db) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client for the app, with an empty database and the app lifespan running."""
    async with get_session_factory()() as session:
        await session.execute(text("TRUNCATE payments, merchants RESTART IDENTITY CASCADE"))
        await session.commit()

    # ASGITransport does not send lifespan events, so run the lifespan by hand
    # (it also disposes the engine, so no connection outlives this test's loop).
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http_client,
    ):
        yield http_client


@pytest.fixture
async def create_merchant(client) -> CreateMerchant:
    """Factory: create an active merchant and return its plain API key.

    There is no merchant endpoint (merchants are created by the admin CLI),
    so this is the one piece of setup written straight to the database.
    """

    async def _create(name: str = "Test merchant") -> str:
        api_key = generate_api_key()
        async with get_session_factory()() as session:
            session.add(Merchant(name=name, api_key_hash=hash_api_key(api_key)))
            await session.commit()
        return api_key

    return _create


@pytest.fixture
async def api_key(create_merchant: CreateMerchant) -> str:
    return await create_merchant("Acme Shop")


@dataclass(frozen=True)
class BankImposter:
    port: int
    url: str

    async def request_count(self) -> int:
        async with httpx.AsyncClient(base_url=TEST_MOUNTEBANK_URL) as admin:
            response = await admin.get(f"/imposters/{self.port}")
        response.raise_for_status()
        return response.json()["numberOfRequests"]


CreateBankImposter = Callable[..., Awaitable[BankImposter]]


@pytest.fixture
async def bank_imposter() -> AsyncIterator[CreateBankImposter]:
    """Factory: an extra bank on `port` that authorizes every payment after `wait_ms`."""
    ports: list[int] = []
    host = urlsplit(TEST_BANK_URL).hostname

    async def _create(port: int, *, wait_ms: int) -> BankImposter:
        imposter = {
            "port": port,
            "protocol": "http",
            "recordRequests": True,
            "stubs": [
                {
                    "responses": [
                        {
                            "is": {
                                "statusCode": 200,
                                "headers": {"Content-Type": "application/json"},
                                "body": {"authorized": True, "authorization_code": "slow-auth"},
                            },
                            "behaviors": [{"wait": wait_ms}],
                        }
                    ]
                }
            ],
        }
        async with httpx.AsyncClient(base_url=TEST_MOUNTEBANK_URL) as admin:
            await admin.delete(f"/imposters/{port}")
            (await admin.post("/imposters", json=imposter)).raise_for_status()
        ports.append(port)
        return BankImposter(port=port, url=f"http://{host}:{port}")

    yield _create

    async with httpx.AsyncClient(base_url=TEST_MOUNTEBANK_URL) as admin:
        for port in ports:
            await admin.delete(f"/imposters/{port}")


@pytest.fixture
async def use_bank(client) -> AsyncIterator[Callable[..., None]]:
    """Point the app at another bank URL with its own timeout for this test."""
    bank_clients: list[BankClient] = []

    def _use(url: str, *, timeout: float) -> None:
        bank_client = BankClient(url, timeout=timeout)
        bank_clients.append(bank_client)
        app.dependency_overrides[get_bank_client] = lambda: bank_client

    yield _use

    app.dependency_overrides.pop(get_bank_client, None)
    for bank_client in bank_clients:
        await bank_client.aclose()
