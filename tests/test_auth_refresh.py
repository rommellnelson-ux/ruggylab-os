"""Integration tests for refresh token endpoints and user deactivation.

Exercises the full /login/access-token → /login/refresh → /login/logout
lifecycle, and verifies that deactivated users cannot authenticate or use
existing refresh tokens.
"""


def _login(client, username: str = "admin", password: str = "change_me_admin_password"):
    resp = client.post(
        "/api/v1/login/access-token",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _auth_headers(client, username="admin", password="change_me_admin_password"):
    token = _login(client, username, password)["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────────────────────────────────────
# Login now returns a refresh token
# ──────────────────────────────────────────────────────────────────────────────


def test_login_returns_refresh_token(client):
    payload = _login(client)
    assert "access_token" in payload
    assert "refresh_token" in payload
    assert payload["token_type"] == "bearer"
    assert len(payload["refresh_token"]) >= 32


# ──────────────────────────────────────────────────────────────────────────────
# /login/refresh
# ──────────────────────────────────────────────────────────────────────────────


def test_refresh_returns_new_token_pair(client):
    payload = _login(client)
    refresh_token = payload["refresh_token"]

    resp = client.post("/api/v1/login/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200, resp.text
    new_payload = resp.json()
    assert "access_token" in new_payload
    assert "refresh_token" in new_payload
    # New refresh token must be different (rotation)
    assert new_payload["refresh_token"] != refresh_token


def test_refresh_token_is_single_use(client):
    """After rotation the old refresh token must be rejected."""
    payload = _login(client)
    old_refresh = payload["refresh_token"]

    # Use it once — should succeed
    resp = client.post("/api/v1/login/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200

    # Use again — must fail (rotated away)
    resp2 = client.post("/api/v1/login/refresh", json={"refresh_token": old_refresh})
    assert resp2.status_code == 401


def test_refresh_with_invalid_token_is_rejected(client):
    resp = client.post("/api/v1/login/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


def test_new_access_token_from_refresh_is_valid(client):
    """Access token obtained via refresh must work for authenticated endpoints."""
    payload = _login(client)
    refresh_resp = client.post(
        "/api/v1/login/refresh", json={"refresh_token": payload["refresh_token"]}
    )
    new_access = refresh_resp.json()["access_token"]
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


# ──────────────────────────────────────────────────────────────────────────────
# /login/logout
# ──────────────────────────────────────────────────────────────────────────────


def test_logout_revokes_refresh_token(client):
    payload = _login(client)
    refresh_token = payload["refresh_token"]

    # Logout
    resp = client.post("/api/v1/login/logout", json={"refresh_token": refresh_token})
    assert resp.status_code == 204

    # Attempt to use revoked token — must fail
    resp2 = client.post("/api/v1/login/refresh", json={"refresh_token": refresh_token})
    assert resp2.status_code == 401


def test_logout_with_unknown_token_is_idempotent(client):
    """Logging out with an unknown token must not raise an error."""
    resp = client.post("/api/v1/login/logout", json={"refresh_token": "ghost-token"})
    assert resp.status_code == 204


# ──────────────────────────────────────────────────────────────────────────────
# User deactivation (is_active)
# ──────────────────────────────────────────────────────────────────────────────


def _create_technician(client, headers):
    resp = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "tech_deactivation_test",
            "password": "Password123!",
            "full_name": "Technicien Test",
            "role": "technician",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_deactivated_user_cannot_login(client):
    admin_headers = _auth_headers(client)
    user = _create_technician(client, admin_headers)
    user_id = user["id"]

    # Deactivate
    resp = client.patch(
        f"/api/v1/users/{user_id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Login attempt must fail
    login_resp = client.post(
        "/api/v1/login/access-token",
        data={"username": "tech_deactivation_test", "password": "Password123!"},
    )
    assert login_resp.status_code == 403


def test_deactivated_user_refresh_token_is_rejected(client):
    admin_headers = _auth_headers(client)
    user = _create_technician(client, admin_headers)
    user_id = user["id"]

    # Login first to get a refresh token
    tokens = client.post(
        "/api/v1/login/access-token",
        data={"username": "tech_deactivation_test", "password": "Password123!"},
    ).json()
    refresh_token = tokens["refresh_token"]

    # Deactivate the user
    client.patch(
        f"/api/v1/users/{user_id}",
        headers=admin_headers,
        json={"is_active": False},
    )

    # Refresh attempt must fail
    resp = client.post("/api/v1/login/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 403


def test_reactivated_user_can_login_again(client):
    admin_headers = _auth_headers(client)
    user = _create_technician(client, admin_headers)
    user_id = user["id"]

    # Deactivate then reactivate
    client.patch(f"/api/v1/users/{user_id}", headers=admin_headers, json={"is_active": False})
    client.patch(f"/api/v1/users/{user_id}", headers=admin_headers, json={"is_active": True})

    login_resp = client.post(
        "/api/v1/login/access-token",
        data={"username": "tech_deactivation_test", "password": "Password123!"},
    )
    assert login_resp.status_code == 200


def test_patch_user_role_and_fullname(client):
    admin_headers = _auth_headers(client)
    user = _create_technician(client, admin_headers)
    user_id = user["id"]

    resp = client.patch(
        f"/api/v1/users/{user_id}",
        headers=admin_headers,
        json={"role": "officer", "full_name": "Officier Promu"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "officer"
    assert data["full_name"] == "Officier Promu"


def test_non_admin_cannot_patch_user(client):
    admin_headers = _auth_headers(client)
    user = _create_technician(client, admin_headers)
    user_id = user["id"]

    # Login as technician
    tech_tokens = client.post(
        "/api/v1/login/access-token",
        data={"username": "tech_deactivation_test", "password": "Password123!"},
    ).json()
    tech_headers = {"Authorization": f"Bearer {tech_tokens['access_token']}"}

    resp = client.patch(
        f"/api/v1/users/{user_id}",
        headers=tech_headers,
        json={"is_active": False},
    )
    assert resp.status_code == 403
