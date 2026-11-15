from typing import Annotated

from fastapi import Depends, Header
from pydantic import StringConstraints

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IdempotencyKeyValue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


async def require_idempotency_key(
    key: Annotated[
        IdempotencyKeyValue,
        Header(
            alias=IDEMPOTENCY_KEY_HEADER,
            description="Unique key per payment attempt; retries must reuse it.",
        ),
    ],
) -> str:
    return key


IdempotencyKey = Annotated[str, Depends(require_idempotency_key)]
