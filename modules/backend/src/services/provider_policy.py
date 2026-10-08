"""Permission and credential origin are separate from provider availability.

BYOK is resolved separately by provider_credentials. Operator-provisioned local
identities retain explicit platform contracts; public identities never inherit credentials.
"""

from fastapi import HTTPException

from ..security import TokenData
from ..config import settings


def require_guest_processing() -> None:
    # Guest is a read-only demonstration, even if old deployment flags/key remain.
    raise HTTPException(403, "A demonstração não processa arquivos. Entre para consultar os serviços disponíveis para sua conta.")


def require_platform_processing() -> None:
    if not (settings.AAI_PLATFORM_ENABLED and settings.AAI_PLATFORM_BUDGET_CENTS > 0
            and (settings.AAI_API_KEY_CONFIGURED or settings.AAI_API_KEY)):
        raise HTTPException(503, "Platform transcription is unavailable")


def require_provider_credential(user: TokenData, provider: str, *, credential_source: str = "platform") -> None:
    if provider == "whisper":
        return
    if credential_source != "platform":
        raise HTTPException(403, "User provider credentials are not supported yet")
    if user.registration_source != "local":
        raise HTTPException(403, "Connect your own provider credential when BYOK becomes available")
    if provider == "assemblyai":
        require_platform_processing()
