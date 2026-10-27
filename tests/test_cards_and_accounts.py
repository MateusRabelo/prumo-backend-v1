from decimal import Decimal
from fastapi.testclient import TestClient
from app.core.config import settings


def test_cards_and_accounts_lifecycle(client: TestClient, auth_headers: dict):
    # 1. Create a bank account with bank name and agency
    acc_res = client.post(
        f"{settings.API_V1_STR}/settings/accounts",
        headers=auth_headers,
        json={
            "name": "Conta Corrente Itaú",
            "account_type": "CHECKING",
            "bank_name": "Itaú Unibanco",
            "agency": "1234",
            "account_number": "56789-0",
            "initial_balance": 5000.00,
            "color": "#EC7000"
        }
    )
    assert acc_res.status_code == 201
    account = acc_res.json()
    assert account["name"] == "Conta Corrente Itaú"
    assert account["bank_name"] == "Itaú Unibanco"
    assert account["agency"] == "1234"
    assert account["account_number"] == "56789-0"

    # 2. Create a credit card
    card_res = client.post(
        f"{settings.API_V1_STR}/cards",
        headers=auth_headers,
        json={
            "name": "Itaú Mastercard Black",
            "card_type": "CREDIT",
            "brand": "Mastercard",
            "bank_name": "Itaú Unibanco",
            "last_digits": "9876",
            "credit_limit": 15000.00,
            "closing_day": 25,
            "due_day": 5,
            "color": "#1F2937",
            "responsible_name": "Carlos",
            "account_id": account["id"]
        }
    )
    assert card_res.status_code == 201
    card = card_res.json()
    assert card["name"] == "Itaú Mastercard Black"
    assert card["brand"] == "Mastercard"
    assert Decimal(str(card["credit_limit"])) == Decimal("15000.00")
    assert Decimal(str(card["available_limit"])) == Decimal("15000.00")
    assert Decimal(str(card["used_limit"])) == Decimal("0.00")

    # 3. List cards
    list_res = client.get(f"{settings.API_V1_STR}/cards", headers=auth_headers)
    assert list_res.status_code == 200
    cards_list = list_res.json()
    assert len(cards_list) >= 1
    found = any(c["id"] == card["id"] for c in cards_list)
    assert found is True

    # 4. Update card limit and due day
    update_res = client.put(
        f"{settings.API_V1_STR}/cards/{card['id']}",
        headers=auth_headers,
        json={
            "credit_limit": 20000.00,
            "due_day": 10
        }
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert Decimal(str(updated["credit_limit"])) == Decimal("20000.00")
    assert updated["due_day"] == 10

    # 5. Delete/Deactivate card
    del_res = client.delete(f"{settings.API_V1_STR}/cards/{card['id']}", headers=auth_headers)
    assert del_res.status_code == 200

    # Verify deactivated card is not returned in list
    after_del = client.get(f"{settings.API_V1_STR}/cards", headers=auth_headers).json()
    assert not any(c["id"] == card["id"] for c in after_del)
