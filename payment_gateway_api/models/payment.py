import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from payment_gateway_api.db import Base
from payment_gateway_api.enums import Currency, PaymentStatus
from payment_gateway_api.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type) -> list[str]:
    # Store the enum *values* ("Authorized") rather than member names ("AUTHORIZED").
    return [member.value for member in enum_cls]


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("expiry_month BETWEEN 1 AND 12", name="expiry_month"),
        CheckConstraint(
            "card_number_last_four ~ '^[0-9]{4}$'", name="card_number_last_four"
        ),
        CheckConstraint(
            "(status = 'Authorized') = (authorization_code IS NOT NULL)",
            name="authorization_code_matches_status",
        ),
        UniqueConstraint(
            "merchant_id",
            "idempotency_key",
            name="uq_payments_merchant_id_idempotency_key",
        ),
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", values_callable=_enum_values)
    )
    card_number_last_four: Mapped[str] = mapped_column(String(4))
    expiry_month: Mapped[int] = mapped_column(SmallInteger)
    expiry_year: Mapped[int] = mapped_column(SmallInteger)
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency, name="currency", values_callable=_enum_values)
    )
    amount: Mapped[int] = mapped_column(BigInteger)
    authorization_code: Mapped[str | None] = mapped_column(String(64))
