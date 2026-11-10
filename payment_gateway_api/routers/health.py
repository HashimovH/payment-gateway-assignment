from typing import Dict

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/liveness")
async def liveness() -> Dict[str, str]:
    return {"status": "alive"}
