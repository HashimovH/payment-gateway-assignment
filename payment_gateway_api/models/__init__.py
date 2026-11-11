# Import every model here so Alembic autogenerate sees all tables.
from payment_gateway_api.models.merchant import Merchant
from payment_gateway_api.models.payment import Payment

__all__ = ["Merchant", "Payment"]
