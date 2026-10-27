from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from app.core.config import settings


def test_card_invoice_lifecycle_and_payment(client: TestClient, auth_headers: dict):
    # 1. Create checking account with R$ 5.000,00
    acc_res = client.post(
        f"{settings.API_V1_STR}/settings/accounts",
        headers=auth_headers,
        json={
            "name": "Conta Corrente Nubank",
            "account_type": "CHECKING",
            "bank_name": "Nubank",
            "initial_balance": 5000.00,
            "color": "#8A05BE"
        }
    )
    assert acc_res.status_code == 201
    account = acc_res.json()
    acc_id = account["id"]

    # 2. Create Credit Card (closing day 25, due day 5)
    today = date.today()
    from app.api.v1.cards import get_current_invoice_period
    from types import SimpleNamespace
    invoice_year, invoice_month = get_current_invoice_period(SimpleNamespace(closing_day=25, due_day=5), today)
    card_res = client.post(
        f"{settings.API_V1_STR}/cards",
        headers=auth_headers,
        json={
            "name": "Nubank Ultravioleta",
            "card_type": "CREDIT",
            "brand": "Mastercard",
            "bank_name": "Nubank",
            "last_digits": "4321",
            "credit_limit": 10000.00,
            "closing_day": 25,
            "due_day": 5,
            "color": "#8A05BE",
            "responsible_name": "Carlos",
            "account_id": acc_id
        }
    )
    assert card_res.status_code == 201
    card = card_res.json()
    card_id = card["id"]

    # 3. Add direct credit card purchase
    tx_res = client.post(
        f"{settings.API_V1_STR}/transactions",
        headers=auth_headers,
        json={
            "date": today.isoformat(),
            "description": "Supermercado Mensal",
            "type": "DESPESA",
            "amount": 350.00,
            "account_id": acc_id,
            "card_id": card_id,
            "responsible_name": "Carlos",
            "is_shared": True,
            "classification": "NECESSIDADE",
            "status": "REALIZADA"
        }
    )
    assert tx_res.status_code == 201

    # 4. Add installment plan on the card: 3 x R$ 100,00
    cat_res = client.get(f"{settings.API_V1_STR}/settings/categories", headers=auth_headers)
    cat_id = cat_res.json()[0]["id"] if cat_res.json() else None

    plan_res = client.post(
        f"{settings.API_V1_STR}/installments",
        headers=auth_headers,
        json={
            "description": "Smartphone Parcelado",
            "category_id": cat_id,
            "card_id": card_id,
            "responsible_name": "Carlos",
            "is_shared": False,
            "total_amount": 300.00,
            "installments_count": 3,
            "purchase_date": today.isoformat(),
            "first_due_date": date(invoice_year, invoice_month, 5).isoformat()
        }
    )
    assert plan_res.status_code == 201

    # 5. Get invoices list
    inv_list_res = client.get(f"{settings.API_V1_STR}/cards/{card_id}/invoices", headers=auth_headers)
    assert inv_list_res.status_code == 200
    invoices = inv_list_res.json()
    assert len(invoices) >= 1

    # Find the active cycle invoice
    active_inv = next((inv for inv in invoices if inv.get("is_current")), invoices[0])
    inv_year = active_inv["year"]
    inv_month = active_inv["month"]

    # 6. Get detail for current active invoice
    detail_res = client.get(
        f"{settings.API_V1_STR}/cards/{card_id}/invoices/{inv_year}/{inv_month}",
        headers=auth_headers
    )
    assert detail_res.status_code == 200
    inv_detail = detail_res.json()
    assert inv_detail["year"] == inv_year
    assert inv_detail["month"] == inv_month
    assert len(inv_detail["items"]) >= 2
    # Total should include R$ 350 direct + R$ 100 installment parcel = R$ 450
    assert Decimal(str(inv_detail["total_amount"])) == Decimal("450.00")
    assert Decimal(str(inv_detail["remaining_amount"])) == Decimal("450.00")
    assert inv_detail["status"] in ["ABERTA", "FECHADA", "VENCIDA"]

    # 7. Pay invoice
    pay_res = client.post(
        f"{settings.API_V1_STR}/cards/{card_id}/invoices/{inv_year}/{inv_month}/pay",
        headers=auth_headers,
        json={
            "account_id": acc_id,
            "payment_date": today.isoformat(),
            "amount": 450.00,
            "notes": "Pagamento da fatura via app"
        }
    )
    assert pay_res.status_code == 200
    paid_inv = pay_res.json()
    assert paid_inv["status"] == "PAGA"
    assert Decimal(str(paid_inv["paid_amount"])) == Decimal("450.00")
    assert Decimal(str(paid_inv["remaining_amount"])) == Decimal("0.00")

    # 8. Check that bank account balance decreased by R$ 450.00 (from 5000 to 4550)
    acc_check = client.get(f"{settings.API_V1_STR}/settings/accounts", headers=auth_headers)
    assert acc_check.status_code == 200
    matching_acc = next(a for a in acc_check.json() if a["id"] == acc_id)
    assert Decimal(str(matching_acc["current_balance"])) == Decimal("4550.00")

    # 9. Verify card limit: 350 is cleared, 1st installment (100) is paid, only remaining 2 installments (200) consume limit!
    card_check = client.get(f"{settings.API_V1_STR}/cards", headers=auth_headers)
    matching_card = next(c for c in card_check.json() if c["id"] == card_id)
    # Remaining pending installments: 2 x 100 = 200.00
    assert Decimal(str(matching_card["used_limit"])) == Decimal("200.00")
    assert Decimal(str(matching_card["available_limit"])) == Decimal("9800.00")
