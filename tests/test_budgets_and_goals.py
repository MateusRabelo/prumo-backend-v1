from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from app.core.config import settings


def get_default_account_and_category(client: TestClient, auth_headers: dict):
    accs = client.get(f"{settings.API_V1_STR}/settings/accounts", headers=auth_headers).json()
    cats = client.get(f"{settings.API_V1_STR}/settings/categories", headers=auth_headers).json()
    return accs[0]["id"], cats[0]["id"]


def test_budget_503020_and_custom(client: TestClient, auth_headers: dict):
    account_id, category_id = get_default_account_and_category(client, auth_headers)

    # 1. Invalid percentages (sum != 100)
    bad_res = client.post(
        f"{settings.API_V1_STR}/budgets/503020",
        headers=auth_headers,
        json={
            "year": 2026,
            "month": 10,
            "estimated_income": 5000.00,
            "needs_percentage": 50.00,
            "wants_percentage": 30.00,
            "savings_percentage": 30.00  # Sum is 110
        }
    )
    assert bad_res.status_code == 400

    # 2. Valid 50/30/20 save
    good_res = client.post(
        f"{settings.API_V1_STR}/budgets/503020",
        headers=auth_headers,
        json={
            "year": 2026,
            "month": 10,
            "estimated_income": 5000.00,
            "needs_percentage": 50.00,
            "wants_percentage": 30.00,
            "savings_percentage": 20.00
        }
    )
    assert good_res.status_code == 200
    b_data = good_res.json()
    assert Decimal(str(b_data["needs_allocated"])) == Decimal("2500.00")
    assert Decimal(str(b_data["wants_allocated"])) == Decimal("1500.00")
    assert Decimal(str(b_data["savings_allocated"])) == Decimal("1000.00")

    # 3. Custom budget
    cust_res = client.post(
        f"{settings.API_V1_STR}/budgets/custom",
        headers=auth_headers,
        json={
            "year": 2026,
            "month": 10,
            "category_id": category_id,
            "limit_amount": 1000.00,
            "alert_threshold_percentage": 80.00
        }
    )
    assert cust_res.status_code == 201
    assert Decimal(str(cust_res.json()["limit_amount"])) == Decimal("1000.00")


def test_goals_lifecycle(client: TestClient, auth_headers: dict):
    account_id, _ = get_default_account_and_category(client, auth_headers)

    # 1. Create Goal
    res = client.post(
        f"{settings.API_V1_STR}/goals/",
        headers=auth_headers,
        json={
            "name": "Reserva de Emergência",
            "description": "6 meses de despesas",
            "target_amount": 10000.00,
            "responsible_name": "Conjunto",
            "is_shared": True
        }
    )
    assert res.status_code == 201
    goal = res.json()
    assert Decimal(str(goal["accumulated_amount"])) == Decimal("0.00")
    assert goal["status"] == "EM_ANDAMENTO"

    # 2. Add Contribution: R$ 4000
    contrib1 = client.post(
        f"{settings.API_V1_STR}/goals/{goal['id']}/contributions",
        headers=auth_headers,
        json={
            "date": str(date.today()),
            "type": "CONTRIBUICAO",
            "amount": 4000.00,
            "account_id": account_id,
            "notes": "Aporte inicial"
        }
    )
    assert contrib1.status_code == 201

    # Check goal progress
    goal_check = client.get(f"{settings.API_V1_STR}/goals/{goal['id']}", headers=auth_headers).json()
    assert Decimal(str(goal_check["accumulated_amount"])) == Decimal("4000.00")
    assert Decimal(str(goal_check["progress_percentage"])) == Decimal("40.00")

    # 3. Add Withdrawal: R$ 1000
    client.post(
        f"{settings.API_V1_STR}/goals/{goal['id']}/contributions",
        headers=auth_headers,
        json={
            "date": str(date.today()),
            "type": "RETIRADA",
            "amount": 1000.00,
            "account_id": account_id,
            "notes": "Retirada imprevisto"
        }
    )
    goal_check2 = client.get(f"{settings.API_V1_STR}/goals/{goal['id']}", headers=auth_headers).json()
    assert Decimal(str(goal_check2["accumulated_amount"])) == Decimal("3000.00")
    assert Decimal(str(goal_check2["progress_percentage"])) == Decimal("30.00")

    # 4. Final Contribution to Reach Target: R$ 7000 (total 10000)
    client.post(
        f"{settings.API_V1_STR}/goals/{goal['id']}/contributions",
        headers=auth_headers,
        json={
            "date": str(date.today()),
            "type": "CONTRIBUICAO",
            "amount": 7000.00,
            "account_id": account_id
        }
    )
    final_goal = client.get(f"{settings.API_V1_STR}/goals/{goal['id']}", headers=auth_headers).json()
    assert Decimal(str(final_goal["accumulated_amount"])) == Decimal("10000.00")
    assert Decimal(str(final_goal["progress_percentage"])) == Decimal("100.00")
    assert final_goal["status"] == "CONCLUIDA"
