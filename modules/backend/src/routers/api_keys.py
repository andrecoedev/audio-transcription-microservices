"""Read-only provider credential status.

Provider keys are infrastructure secrets supplied to API/worker processes by
the deployment environment. The former shared JSON write path is deliberately
retired; returning even a key prefix is avoided.
"""

from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..security import TokenData, require_admin


router = APIRouter()


def _key_status() -> dict:
    return {
        "source": "environment",
        "mutable": False,
        "hf_token": {"configured": settings.HF_TOKEN_CONFIGURED or bool(settings.HF_TOKEN)},
        "aai_api_key": {"configured": settings.AAI_API_KEY_CONFIGURED or bool(settings.AAI_API_KEY)},
        "gemini_api_key": {"configured": settings.GEMINI_API_KEY_CONFIGURED or bool(settings.GEMINI_API_KEY)},
    }


@router.get("/api-keys")
async def get_api_keys_status(
    _current_user: TokenData = Depends(require_admin),
):
    return _key_status()


@router.post("/api-keys", status_code=410)
async def update_api_keys_retired(
    _current_user: TokenData = Depends(require_admin),
):
    raise HTTPException(
        status_code=410,
        detail="Runtime credential updates were retired; configure provider secrets in the deployment environment and restart workers",
    )
