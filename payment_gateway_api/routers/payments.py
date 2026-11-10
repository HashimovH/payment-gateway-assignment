from fastapi import APIRouter, Depends, HTTPException, status

from payment_gateway_api.dependencies.merchants import get_current_merchant

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(get_current_merchant)],
)


@router.post("", status_code=status.HTTP_201_CREATED)
async def process_payment():
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet")


@router.get("/{payment_id}")
async def get_payment(payment_id: str):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet")
