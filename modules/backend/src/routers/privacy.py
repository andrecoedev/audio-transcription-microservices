"""Self-service account data; caller identity is never an HTTP parameter."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import TokenData, get_authenticated_user
from ..services.privacy import export_user_data
from ..services.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/account", tags=["privacy"])


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
