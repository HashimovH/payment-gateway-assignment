from enum import StrEnum


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


class PaymentStatus(StrEnum):
    AUTHORIZED = "Authorized"
    DECLINED = "Declined"
    REJECTED = "Rejected"
