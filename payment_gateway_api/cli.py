"""Admin commands.

python -m payment_gateway_api.cli create-merchant "Acme Shop"
"""

import argparse
import asyncio

from payment_gateway_api.auth import generate_api_key, hash_api_key
from payment_gateway_api.db import get_engine, get_session_factory
from payment_gateway_api.models.merchant import Merchant
from payment_gateway_api.repositories.merchants import MerchantRepository


async def create_merchant(name: str) -> None:
    api_key = generate_api_key()
    merchant = Merchant(name=name, api_key_hash=hash_api_key(api_key))

    async with get_session_factory()() as session:
        await MerchantRepository(session).add(merchant)
    await get_engine().dispose()

    print(f"Merchant created: {merchant.id} ({merchant.name})")
    print(f"API key (shown once, store it now): {api_key}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="payment_gateway_api.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-merchant", help="Create a merchant and its API key")
    create.add_argument("name")

    args = parser.parse_args()
    if args.command == "create-merchant":
        asyncio.run(create_merchant(args.name))


if __name__ == "__main__":
    main()
