from enum import StrEnum


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


class PaymentStatus(StrEnum):
    PENDING = "Pending"
    AUTHORIZED = "Authorized"
    DECLINED = "Declined"
