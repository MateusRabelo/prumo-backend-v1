from fastapi.testclient import TestClient
from app.core.config import settings


def test_dashboard_metrics(client: TestClient, auth_headers: dict):
    res = client.get(f"{settings.API_V1_STR}/dashboard/metrics?period=this_month", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "realized_income" in data
    assert "realized_expense" in data
    assert "net_result" in data
    assert "category_spending" in data
    assert "responsible_spending" in data
    assert "cash_flow_timeline" in data
    assert "total_account_balance" in data


def test_family_isolation_and_security(client: TestClient, auth_headers: dict):
    # Register a different user in their own family
    res_b = client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={
            "email": "user_b@example.com",
            "full_name": "Outro Usuário",
            "password": "strongPasswordB123"
        }
    )
    assert res_b.status_code == 201
    user_b_token = res_b.json()["access_token"]
    user_b_family = res_b.json()["current_family_id"]

    # User B tries to access User A's family using User A's family ID in header
    headers_tampered = {
        "Authorization": f"Bearer {user_b_token}",
        "X-Family-Id": auth_headers["X-Family-Id"]
    }
    denied_res = client.get(f"{settings.API_V1_STR}/transactions/", headers=headers_tampered)
    assert denied_res.status_code == 403
    assert "Acesso negado" in denied_res.json()["detail"]
