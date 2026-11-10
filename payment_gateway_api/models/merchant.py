from sqlalchemy import String, true
from sqlalchemy.orm import Mapped, mapped_column

from payment_gateway_api.db import Base
from payment_gateway_api.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Merchant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "merchants"

    name: Mapped[str] = mapped_column(String(255))
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    def __repr__(self) -> str:
        return f"Merchant(id={self.id!s}, name={self.name!r}, is_active={self.is_active})"
