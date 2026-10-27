from fastapi.testclient import TestClient
from app.core.config import settings


def test_register_and_login(client: TestClient):
    # Register new user
    res = client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={
            "email": "sofia@example.com",
            "full_name": "Sofia Rabelo",
            "password": "strongPassword987"
        }
    )
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "sofia@example.com"
    assert data["current_family_id"] is not None

    # Login with correct credentials
    login_res = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={
            "email": "sofia@example.com",
            "password": "strongPassword987"
        }
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

    # Login with wrong password
    bad_login = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={
            "email": "sofia@example.com",
            "password": "wrongpassword"
        }
    )
    assert bad_login.status_code == 401


def test_me_and_my_families(client: TestClient, auth_headers: dict):
    res = client.get(f"{settings.API_V1_STR}/auth/me", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["email"] == "testuser@example.com"

    f_res = client.get(f"{settings.API_V1_STR}/auth/my-families", headers=auth_headers)
    assert f_res.status_code == 200
    assert len(f_res.json()) >= 1


def test_change_password(client: TestClient, auth_headers: dict):
    res = client.post(
        f"{settings.API_V1_STR}/auth/change-password",
        headers=auth_headers,
        json={
            "current_password": "secretpassword123",
            "new_password": "newStrongPassword123"
        }
    )
    assert res.status_code == 200
    assert res.json()["message"] == "Senha alterada com sucesso"
