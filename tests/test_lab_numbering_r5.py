"""Régressions R5 — numérotation annuelle des échantillons."""

from __future__ import annotations

import datetime as dt
import uuid

from app.db.session import SessionLocal
from app.models import Sample


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_r5_generated_lab_number_uses_highest_sequence_after_gap(client) -> None:
    year = dt.datetime.now(dt.UTC).year
    suffix = uuid.uuid4().hex[:8]
    with SessionLocal() as setup:
        setup.add_all(
            [
                Sample(
                    barcode=f"R5-GAP-A-{suffix}",
                    lab_number=f"{year}-000001",
                    status="Recu",
                ),
                Sample(
                    barcode=f"R5-GAP-C-{suffix}",
                    lab_number=f"{year}-000003",
                    status="Recu",
                ),
            ]
        )
        setup.commit()

    response = client.post(
        "/api/v1/samples",
        headers=_auth(client),
        json={"barcode": f"R5-GAP-NEXT-{suffix}", "status": "Recu"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["lab_number"] == f"{year}-000004"
