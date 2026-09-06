"""Persistência de chaves; somente o worker as usa para inicializar engines."""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..api_keys_manager import api_keys_manager
from ..config import settings
from ..schemas import ApiKeysUpdate
from ..security import TokenData, require_admin_when

logger = logging.getLogger(__name__)
router = APIRouter()


def _key_status() -> dict:
    return {
        "hf_token": {
            "configured": bool(settings.HF_TOKEN),
            "value": f"{settings.HF_TOKEN[:8]}..." if settings.HF_TOKEN else None,
        },
        "aai_api_key": {
            "configured": bool(settings.AAI_API_KEY),
            "value": (
                f"{settings.AAI_API_KEY[:8]}..." if settings.AAI_API_KEY else None
            ),
        },
        "gemini_api_key": {
            "configured": bool(settings.GEMINI_API_KEY),
            "value": (
                f"{settings.GEMINI_API_KEY[:8]}..."
                if settings.GEMINI_API_KEY
                else None
            ),
        },
    }


@router.get("/api-keys")
async def get_api_keys_status(
    current_user: Optional[TokenData] = Depends(
        require_admin_when(settings.AUTH_PROTECT_API_KEYS)
    ),
):
    """Retorna somente metadados seguros das chaves configuradas."""
    return _key_status()


@router.post("/api-keys")
async def update_api_keys(
    keys: ApiKeysUpdate,
    current_user: Optional[TokenData] = Depends(
        require_admin_when(settings.AUTH_PROTECT_API_KEYS)
    ),
):
    """Persiste chaves sem importar ou inicializar engines no processo HTTP."""
    keys_to_save = {
        setting_name: value.strip()
        for setting_name, value in {
            "HF_TOKEN": keys.hf_token,
            "AAI_API_KEY": keys.aai_api_key,
            "GEMINI_API_KEY": keys.gemini_api_key,
        }.items()
        if value and value.strip()
    }
    if not keys_to_save:
        raise HTTPException(status_code=400, detail="No API keys were provided")

    try:
        api_keys_manager.set_multiple(keys_to_save)
        for setting_name, value in keys_to_save.items():
            setattr(settings, setting_name, value)
            os.environ[setting_name] = value
        logger.info("API key configuration updated: %s", list(keys_to_save))
    except Exception:
        logger.exception("Unable to persist API key configuration")
        raise HTTPException(
            status_code=500,
            detail="Unable to persist API key configuration",
        )

    return {
        "success": True,
        "keys_saved": True,
        "worker_restart_required": True,
        "message": "Keys saved. Restart RQ workers to load the new configuration.",
        "updated_models": [],
        "errors": [],
        "current_status": _key_status(),
    }
