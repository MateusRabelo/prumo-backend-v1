from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from app.core.config import settings


def get_default_account_and_category(client: TestClient, auth_headers: dict):
    accs = client.get(f"{settings.API_V1_STR}/settings/accounts", headers=auth_headers).json()
    cats = client.get(f"{settings.API_V1_STR}/settings/categories", headers=auth_headers).json()
    return accs[0]["id"], cats[0]["id"]


def test_installments_lifecycle(client: TestClient, auth_headers: dict):
    account_id, category_id = get_default_account_and_category(client, auth_headers)

    # 1. Create installment plan: R$ 1000 in 3 installments
    plan_res = client.post(
        f"{settings.API_V1_STR}/installments/",
        headers=auth_headers,
        json={
            "description": "Geladeira Frost Free",
            "category_id": category_id,
            "account_id": account_id,
            "responsible_name": "Conjunto",
            "is_shared": True,
            "total_amount": 1000.00,
            "installments_count": 3,
            "purchase_date": str(date.today()),
            "first_due_date": str(date.today()),
            "notes": "Compra parcelada em 3x sem juros"
        }
    )
    assert plan_res.status_code == 201
    plan = plan_res.json()
    assert plan["installments_count"] == 3
    assert len(plan["installments"]) == 3
    
    # Check exact cent distribution
    inst_amounts = [Decimal(str(i["amount"])) for i in plan["installments"]]
    assert inst_amounts == [Decimal("333.34"), Decimal("333.33"), Decimal("333.33")]
    assert sum(inst_amounts) == Decimal("1000.00")

    # 2. Pay installment 1
    inst_1 = plan["installments"][0]
    pay_res = client.post(
        f"{settings.API_V1_STR}/installments/installments/{inst_1['id']}/pay",
        headers=auth_headers,
        json={"payment_date": str(date.today()), "account_id": account_id}
    )
    assert pay_res.status_code == 200
    paid_inst = pay_res.json()
    assert paid_inst["status"] == "PAGA"
    assert paid_inst["transaction_id"] is not None

    # Check that a realized transaction was created
    tx_res = client.get(f"{settings.API_V1_STR}/transactions/{paid_inst['transaction_id']}", headers=auth_headers)
    assert tx_res.status_code == 200
    assert tx_res.json()["status"] == "REALIZADA"
    assert Decimal(str(tx_res.json()["amount"])) == Decimal("333.34")

    # 3. Cannot pay the same installment again
    repeat_pay = client.post(
        f"{settings.API_V1_STR}/installments/installments/{inst_1['id']}/pay",
        headers=auth_headers,
        json={"payment_date": str(date.today())}
    )
    assert repeat_pay.status_code == 409

    # 4. Calendar overview
    cal_res = client.get(f"{settings.API_V1_STR}/installments/calendar/overview?months_ahead=3", headers=auth_headers)
    assert cal_res.status_code == 200
    assert len(cal_res.json()) >= 1

    # 5. Cancel plan
    cancel_res = client.post(f"{settings.API_V1_STR}/installments/{plan['id']}/cancel", headers=auth_headers)
    assert cancel_res.status_code == 200

    # Verify that installment 1 remains PAGA and installments 2 & 3 are CANCELADA
    plan_refreshed = client.get(f"{settings.API_V1_STR}/installments/{plan['id']}", headers=auth_headers).json()
    assert plan_refreshed["status"] == "CANCELLED"
    assert plan_refreshed["installments"][0]["status"] == "PAGA"
    assert plan_refreshed["installments"][1]["status"] == "CANCELADA"
    assert plan_refreshed["installments"][2]["status"] == "CANCELADA"
