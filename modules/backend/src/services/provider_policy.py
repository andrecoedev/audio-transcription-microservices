"""Permission and credential origin are separate from provider availability.

BYOK storage/resolution is deferred to P4-03/P4-04. Operator-provisioned local
identities retain private contracts; public identities never inherit credentials.
"""

from fastapi import HTTPException

from ..security import TokenData


def require_provider_credential(user: TokenData, provider: str, *, credential_source: str = "platform") -> None:
    if provider == "whisper":
        return
    if credential_source != "platform":
        raise HTTPException(403, "User provider credentials are not supported yet")
    if user.registration_source != "local":
        raise HTTPException(403, "Connect your own provider credential when BYOK becomes available")
