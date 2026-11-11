import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from payment_gateway_api.db import Base
from payment_gateway_api.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("status IN ('Authorized', 'Declined')", name="status"),
        CheckConstraint("amount > 0", name="amount"),
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("merchants.id"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    card_number_last_four: Mapped[str] = mapped_column(String(4))
    expiry_month: Mapped[int] = mapped_column(SmallInteger)
    expiry_year: Mapped[int] = mapped_column(SmallInteger)
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[int] = mapped_column(BigInteger)
    authorization_code: Mapped[str | None] = mapped_column(String(64))
