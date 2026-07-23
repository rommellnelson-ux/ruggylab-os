"""Preuve PostgreSQL de sérialisation des transitions de non-conformité."""

from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from app.api.v1.endpoints import quality as quality_endpoint
from app.api.v1.endpoints.quality import transition_non_conformity
from app.db.session import SessionLocal, engine
from app.models import AuditEvent, NonConformity, User, UserRole
from app.schemas.quality import NCStatus, NonConformityTransition

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Ce test valide le verrou de ligne NC sous PostgreSQL.",
)


def test_concurrent_nc_transitions_observe_committed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    with SessionLocal() as setup:
        user = User(
            username=f"quality_pg_{suffix}",
            hashed_password="synthetic-not-used",
            role=UserRole.ADMIN,
            is_active=True,
        )
        setup.add(user)
        setup.flush()
        nc = NonConformity(
            title=f"NC synthétique concurrence {suffix}",
            description="Aucune donnée patient.",
            source="manual",
            severity="major",
            status="open",
            detected_by_id=user.id,
        )
        setup.add(nc)
        setup.commit()
        user_id = user.id
        nc_id = nc.id

    first_transition_holds_lock = threading.Event()
    release_first_transition = threading.Event()
    original_log_audit_event = quality_endpoint.log_audit_event

    def pause_first_transition(*args: Any, **kwargs: Any) -> AuditEvent:
        payload = kwargs.get("payload")
        if (
            kwargs.get("event_type") == "quality.nc.transition"
            and isinstance(payload, dict)
            and payload.get("to") == "analysis"
        ):
            first_transition_holds_lock.set()
            assert release_first_transition.wait(timeout=5)
        return original_log_audit_event(*args, **kwargs)

    monkeypatch.setattr(quality_endpoint, "log_audit_event", pause_first_transition)

    def transition(target: NCStatus) -> str:
        with SessionLocal() as db:
            current_user = db.get(User, user_id)
            assert current_user is not None
            outcome = transition_non_conformity(
                nc_id,
                NonConformityTransition(status=target),
                db,
                current_user,
            )
            return outcome.status

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        first = executor.submit(transition, "analysis")
        assert first_transition_holds_lock.wait(timeout=5)
        second = executor.submit(transition, "closed")
        time.sleep(0.25)
        assert not second.done(), "la seconde transition n'a pas attendu le verrou NC"

        release_first_transition.set()
        assert first.result(timeout=10) == "analysis"
        assert second.result(timeout=10) == "closed"

        with SessionLocal() as verification:
            persisted = verification.get(NonConformity, nc_id)
            assert persisted is not None
            assert persisted.status == "closed"
            events = (
                verification.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "quality.nc.transition",
                    AuditEvent.entity_id == str(nc_id),
                )
                .order_by(AuditEvent.id.asc())
                .all()
            )
            assert [json.loads(event.payload or "{}") for event in events] == [
                {"from": "open", "to": "analysis"},
                {"from": "analysis", "to": "closed"},
            ]
    finally:
        release_first_transition.set()
        executor.shutdown(wait=True, cancel_futures=True)
        with SessionLocal() as cleanup:
            cleanup.query(AuditEvent).filter(
                AuditEvent.entity_type == "non_conformity",
                AuditEvent.entity_id == str(nc_id),
            ).delete(synchronize_session=False)
            stored_nc = cleanup.get(NonConformity, nc_id)
            if stored_nc is not None:
                cleanup.delete(stored_nc)
            stored_user = cleanup.get(User, user_id)
            if stored_user is not None:
                cleanup.delete(stored_user)
            cleanup.commit()
