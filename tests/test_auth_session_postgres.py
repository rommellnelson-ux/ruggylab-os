"""Preuve PostgreSQL de sérialisation entre connexion et mise à jour sensible."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

from app.api.v1.endpoints import login as login_endpoint
from app.api.v1.endpoints import users as users_endpoint
from app.core.security import get_password_hash, hash_token
from app.db.session import SessionLocal, engine
from app.models import AuditEvent, RefreshToken, User, UserRole
from app.schemas.auth import RefreshRequest
from app.schemas.user import UserUpdate

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Ce test valide le verrou utilisateur sous PostgreSQL.",
)


def test_password_change_serializes_with_concurrent_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    old_password = "SyntheticOld123!"
    new_password = "SyntheticNew456!"
    with SessionLocal() as setup:
        admin = User(
            username=f"auth_admin_pg_{suffix}",
            hashed_password=get_password_hash("SyntheticAdmin123!"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        target = User(
            username=f"auth_user_pg_{suffix}",
            hashed_password=get_password_hash(old_password),
            role=UserRole.TECHNICIAN,
            is_active=True,
        )
        setup.add_all([admin, target])
        setup.commit()
        admin_id = admin.id
        target_id = target.id
        target_username = target.username

    login_holds_user_lock = threading.Event()
    release_login = threading.Event()
    original_verify_password = login_endpoint.verify_password

    def pause_password_verification(plain_password: str, hashed_password: str) -> bool:
        verified = original_verify_password(plain_password, hashed_password)
        if plain_password == old_password:
            login_holds_user_lock.set()
            assert release_login.wait(timeout=5)
        return verified

    monkeypatch.setattr(login_endpoint, "verify_password", pause_password_verification)

    def log_in() -> Any:
        with SessionLocal() as db:
            form = SimpleNamespace(
                username=target_username,
                password=old_password,
                scopes=[],
            )
            return login_endpoint.login_access_token(db=db, form_data=form)

    def change_password() -> None:
        with SessionLocal() as db:
            current_admin = db.get(User, admin_id)
            assert current_admin is not None
            users_endpoint.update_user(
                user_id=target_id,
                payload=UserUpdate(password=new_password),
                db=db,
                current_user=current_admin,
            )

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        login_future = executor.submit(log_in)
        assert login_holds_user_lock.wait(timeout=5)
        update_future = executor.submit(change_password)
        time.sleep(0.25)
        assert not update_future.done(), "la mise à jour n'a pas attendu le verrou utilisateur"

        release_login.set()
        tokens = login_future.result(timeout=10)
        update_future.result(timeout=10)

        with SessionLocal() as verification:
            target = verification.get(User, target_id)
            stored_refresh = (
                verification.query(RefreshToken)
                .filter(RefreshToken.token_hash == hash_token(tokens.refresh_token))
                .one()
            )
            assert target is not None
            assert target.auth_version == 1
            assert stored_refresh.revoked_at is not None
    finally:
        release_login.set()
        executor.shutdown(wait=True, cancel_futures=True)
        with SessionLocal() as cleanup:
            cleanup.query(AuditEvent).filter(
                AuditEvent.event_type == "user.update",
                AuditEvent.entity_type == "user",
                AuditEvent.entity_id == str(target_id),
            ).delete(synchronize_session=False)
            cleanup.query(RefreshToken).filter(RefreshToken.user_id == target_id).delete(
                synchronize_session=False
            )
            for user_id in (target_id, admin_id):
                stored_user = cleanup.get(User, user_id)
                if stored_user is not None:
                    cleanup.delete(stored_user)
            cleanup.commit()


def test_password_change_serializes_with_concurrent_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    with SessionLocal() as setup:
        admin = User(
            username=f"refresh_admin_pg_{suffix}",
            hashed_password=get_password_hash("SyntheticAdmin123!"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        target = User(
            username=f"refresh_user_pg_{suffix}",
            hashed_password=get_password_hash("SyntheticOld123!"),
            role=UserRole.TECHNICIAN,
            is_active=True,
        )
        setup.add_all([admin, target])
        setup.flush()
        initial_tokens = login_endpoint._issue_tokens(target, setup)
        admin_id = admin.id
        target_id = target.id

    refresh_holds_user_lock = threading.Event()
    release_refresh = threading.Event()
    original_issue_tokens = login_endpoint._issue_tokens

    def pause_token_issue(*args: Any, **kwargs: Any) -> Any:
        refresh_holds_user_lock.set()
        assert release_refresh.wait(timeout=5)
        return original_issue_tokens(*args, **kwargs)

    monkeypatch.setattr(login_endpoint, "_issue_tokens", pause_token_issue)

    def refresh() -> Any:
        with SessionLocal() as db:
            return login_endpoint.refresh_access_token(
                payload=RefreshRequest(refresh_token=initial_tokens.refresh_token),
                db=db,
            )

    def change_password() -> None:
        with SessionLocal() as db:
            current_admin = db.get(User, admin_id)
            assert current_admin is not None
            users_endpoint.update_user(
                user_id=target_id,
                payload=UserUpdate(password="SyntheticNew456!"),
                db=db,
                current_user=current_admin,
            )

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        refresh_future = executor.submit(refresh)
        assert refresh_holds_user_lock.wait(timeout=5)
        update_future = executor.submit(change_password)
        time.sleep(0.25)
        assert not update_future.done(), "la mise à jour n'a pas attendu le verrou utilisateur"

        release_refresh.set()
        rotated_tokens = refresh_future.result(timeout=10)
        update_future.result(timeout=10)

        with SessionLocal() as verification:
            target = verification.get(User, target_id)
            rotated_refresh = (
                verification.query(RefreshToken)
                .filter(RefreshToken.token_hash == hash_token(rotated_tokens.refresh_token))
                .one()
            )
            assert target is not None
            assert target.auth_version == 1
            assert rotated_refresh.revoked_at is not None
    finally:
        release_refresh.set()
        executor.shutdown(wait=True, cancel_futures=True)
        with SessionLocal() as cleanup:
            cleanup.query(AuditEvent).filter(
                AuditEvent.event_type == "user.update",
                AuditEvent.entity_type == "user",
                AuditEvent.entity_id == str(target_id),
            ).delete(synchronize_session=False)
            cleanup.query(RefreshToken).filter(RefreshToken.user_id == target_id).delete(
                synchronize_session=False
            )
            for user_id in (target_id, admin_id):
                stored_user = cleanup.get(User, user_id)
                if stored_user is not None:
                    cleanup.delete(stored_user)
            cleanup.commit()
