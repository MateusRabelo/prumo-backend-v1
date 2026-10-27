from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from app.core.config import settings


def get_default_account_and_category(client: TestClient, auth_headers: dict):
    accs = client.get(f"{settings.API_V1_STR}/settings/accounts", headers=auth_headers).json()
    cats = client.get(f"{settings.API_V1_STR}/settings/categories", headers=auth_headers).json()
    return accs[0]["id"], cats[0]["id"]


def test_transactions_crud_and_filters(client: TestClient, auth_headers: dict):
    account_id, category_id = get_default_account_and_category(client, auth_headers)

    # 1. Create Realized Income
    res_inc = client.post(
        f"{settings.API_V1_STR}/transactions/",
        headers=auth_headers,
        json={
            "date": str(date.today()),
            "description": "Salário Mensal",
            "type": "RECEITA",
            "amount": 6000.00,
            "category_id": category_id,
            "account_id": account_id,
            "responsible_name": "Mateus",
            "is_shared": False,
            "classification": "NECESSIDADE",
            "status": "REALIZADA"
        }
    )
    assert res_inc.status_code == 201
    inc_id = res_inc.json()["id"]

    # 2. Create Realized Expense
    res_exp = client.post(
        f"{settings.API_V1_STR}/transactions/",
        headers=auth_headers,
        json={
            "date": str(date.today()),
            "description": "Supermercado Mensal",
            "type": "DESPESA",
            "amount": 1500.00,
            "category_id": category_id,
            "account_id": account_id,
            "responsible_name": "Conjunto",
            "is_shared": True,
            "classification": "NECESSIDADE",
            "status": "REALIZADA"
        }
    )
    assert res_exp.status_code == 201
    exp_id = res_exp.json()["id"]

    # 3. Create Pending Expense
    res_pending = client.post(
        f"{settings.API_V1_STR}/transactions/",
        headers=auth_headers,
        json={
            "date": str(date.today()),
            "description": "Conta de Energia",
            "type": "DESPESA",
            "amount": 250.00,
            "category_id": category_id,
            "account_id": account_id,
            "responsible_name": "Mateus",
            "is_shared": False,
            "classification": "NECESSIDADE",
            "status": "PENDENTE"
        }
    )
    assert res_pending.status_code == 201

    # 4. List and verify summary calculations
    list_res = client.get(f"{settings.API_V1_STR}/transactions/", headers=auth_headers)
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] >= 3
    summary = data["summary"]
    
    # Realized Income should be 6000, Realized Expense should be 1500 (pending 250 is NOT included in realized!)
    assert Decimal(str(summary["total_realized_income"])) == Decimal("6000.00")
    assert Decimal(str(summary["total_realized_expense"])) == Decimal("1500.00")
    assert Decimal(str(summary["realized_net"])) == Decimal("4500.00")
    assert Decimal(str(summary["total_pending_expense"])) == Decimal("250.00")

    # 5. Duplicate transaction
    dup_res = client.post(f"{settings.API_V1_STR}/transactions/{exp_id}/duplicate", headers=auth_headers)
    assert dup_res.status_code == 201
    assert "Cópia" in dup_res.json()["description"]

    # 6. Delete transaction (soft delete)
    del_res = client.delete(f"{settings.API_V1_STR}/transactions/{inc_id}", headers=auth_headers)
    assert del_res.status_code == 200

    # 7. Export CSV
    csv_res = client.get(f"{settings.API_V1_STR}/transactions/export/csv", headers=auth_headers)
    assert csv_res.status_code == 200
    assert "Supermercado Mensal" in csv_res.text
