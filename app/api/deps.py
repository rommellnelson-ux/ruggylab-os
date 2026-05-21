import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/login/access-token",
    scopes={
        "read": "Read access",
        "write": "Write access",
        "admin": "Administrative actions",
    },
)


def get_current_user(
    security_scopes: SecurityScopes,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> User:
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Impossible de valider les identifiants.",
        headers={"WWW-Authenticate": authenticate_value},
    )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
        token_scopes = payload.get("scopes", [])
        if not username:
            raise credentials_exception
    except InvalidTokenError as exc:
        raise credentials_exception from exc

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise credentials_exception

    # Verify required scopes are present in the token
    for scope in security_scopes.scopes:
        if scope not in token_scopes:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Permissions insuffisantes.",
                headers={"WWW-Authenticate": authenticate_value},
            )

    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte utilisateur desactive.",
        )
    return current_user


def require_officer(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role not in {UserRole.OFFICER, UserRole.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acces reserve aux officiers et administrateurs.",
        )
    return current_user


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acces reserve aux administrateurs.",
        )
    return current_user
