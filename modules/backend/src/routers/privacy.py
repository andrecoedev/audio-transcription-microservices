"""Self-service account data; caller identity is never an HTTP parameter."""
import time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, SecretStr, Field
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import TokenData, get_authenticated_user, oauth2_scheme, verify_password
from ..services.privacy import export_user_data, erase_user_data
from ..services.rate_limit import enforce_rate_limit
from ..services.firebase_identity import verify_firebase_token, find_firebase_user
from ..services.transcription_deletion import ActiveTranscriptionError
from ..utils.http_limits import BodyLimitedRoute

router = APIRouter(prefix="/account", tags=["privacy"], route_class=BodyLimitedRoute)


class DeleteAccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["EXCLUIR"]
    password: SecretStr | None = Field(None, max_length=72)


@router.delete("")
def delete_account(body: DeleteAccountInput, request: Request,
                   db: Session = Depends(get_db),
                   principal: TokenData = Depends(get_authenticated_user),
                   token: str = Depends(oauth2_scheme)):
    if request.query_params:
        raise HTTPException(422, "Esta ação não aceita filtros de conta.")
    enforce_rate_limit(request, "privacy-delete-user", str(principal.user_id))
    try:
        user = db.query(User).filter_by(id=principal.user_id).with_for_update(key_share=True, nowait=True).populate_existing().one_or_none()
    except OperationalError as error:
        db.rollback()
        if getattr(error.orig, "sqlstate", None) == "55P03":
            raise HTTPException(409, "A conta está em uso. Aguarde a operação terminar e tente novamente.") from None
        raise HTTPException(503, "Não foi possível excluir a conta agora. Tente novamente.") from None
    if user is None or not user.is_active:
        raise HTTPException(401, "Entre na sua conta para continuar.")
    if principal.auth_provider == "firebase":
        identity = verify_firebase_token(token)
        linked = find_firebase_user(db, identity)
        age = int(time.time()) - identity.auth_time
        if linked is None or linked.id != user.id or not 0 <= age <= 300:
            raise HTTPException(403, "Confirme sua identidade novamente antes de excluir a conta.")
    elif body.password is None or not verify_password(body.password.get_secret_value(), user.hashed_password):
        raise HTTPException(403, "Confirme sua senha antes de excluir a conta.")
    try:
        result = erase_user_data(db, user)
    except ActiveTranscriptionError:
        db.rollback()
        raise HTTPException(409, "Aguarde os processamentos em andamento antes de excluir a conta.") from None
    return {"account_deleted": True, "cleanup_pending": result.cleanup_pending,
            "identity_cleanup_pending": result.identity_cleanup_pending}


@router.get("/data")
def export_account_data(request: Request, response: Response,
                        db: Session = Depends(get_db),
                        principal: TokenData = Depends(get_authenticated_user)):
    if request.query_params:
        raise HTTPException(422, "Esta exportação não aceita filtros de conta.")
    user = db.get(User, principal.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "Entre na sua conta para exportar seus dados.")
    enforce_rate_limit(request, "privacy-export-user", str(user.id))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = 'attachment; filename="usagi-data.json"'
    return export_user_data(db, user)
