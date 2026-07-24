from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_admin
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models import RefreshToken, User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.audit import log_audit_event
from app.utils.datetime_utils import utcnow_naive

router = APIRouter(prefix="/users")


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_active_user)) -> User:
    return current_user


@router.get("", response_model=list[UserRead], dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return db.query(User).order_by(User.id.desc()).all()


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> User:
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Utilisateur deja existant: {payload.username}.",
        )

    user = User(
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        unit=payload.unit,
    )
    db.add(user)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="user.create",
        entity_type="user",
        entity_id=str(user.id),
        payload={"username": payload.username, "role": payload.role.value},
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(require_admin)],
)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Partial update: role, full_name, or is_active (admin only)."""
    target = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Utilisateur introuvable: {user_id}.",
        )

    changes: dict = {}
    security_changed = False
    if payload.full_name is not None:
        target.full_name = payload.full_name
        changes["full_name"] = payload.full_name
    if payload.role is not None:
        target.role = payload.role
        changes["role"] = payload.role.value
    if payload.is_active is not None and payload.is_active != target.is_active:
        target.is_active = payload.is_active
        changes["is_active"] = payload.is_active
        security_changed = True
    if payload.password is not None:
        target.hashed_password = get_password_hash(payload.password)
        changes["password_changed"] = True
        security_changed = True
    if payload.unit is not None:
        target.unit = payload.unit
        changes["unit"] = payload.unit

    if security_changed:
        target.auth_version += 1
        db.query(RefreshToken).filter(
            RefreshToken.user_id == target.id,
            RefreshToken.revoked_at.is_(None),
        ).update(
            {RefreshToken.revoked_at: utcnow_naive()},
            synchronize_session=False,
        )
        changes["sessions_revoked"] = True

    log_audit_event(
        db,
        user=current_user,
        event_type="user.update",
        entity_type="user",
        entity_id=str(target.id),
        payload={"username": target.username, **changes},
    )
    db.commit()
    db.refresh(target)
    return target
