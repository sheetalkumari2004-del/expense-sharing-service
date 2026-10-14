import pytest


@pytest.fixture
def trip(client):
    """Goa Trip with Mohit (1), Rahul (2), Ankit (3)."""
    group = client.post("/groups", json={"name": "Goa Trip"}).json()
    ids = {}
    for name in ("Mohit", "Rahul", "Ankit"):
        user = client.post("/users", json={"name": name}).json()
        client.post(f"/groups/{group['id']}/members", json={"user_id": user["id"]})
        ids[name] = user["id"]
    return {"group": group["id"], **ids}


def add_expense(client, trip, payer, amount, description="Dinner"):
    return client.post(
        "/expenses",
        json={"group_id": trip["group"], "paid_by": trip[payer], "amount": amount,
              "description": description},
    )


def test_spec_example_dinner(client, trip):
    res = add_expense(client, trip, "Mohit", 1200)
    assert res.status_code == 201
    body = res.json()
    assert body["paid_by"] == "Mohit" and body["amount"] == 1200
    assert [s["amount"] for s in body["splits"]] == [400, 400, 400]

    balances = client.get(f"/groups/{trip['group']}/balances").json()
    assert balances == {"Rahul": {"owes": {"Mohit": 400}}, "Ankit": {"owes": {"Mohit": 400}}}


def test_list_expenses(client, trip):
    add_expense(client, trip, "Mohit", 1200, "Dinner")
    add_expense(client, trip, "Rahul", 300, "Cab")
    expenses = client.get(f"/groups/{trip['group']}/expenses").json()
    assert [(e["description"], e["amount"], e["paid_by"]) for e in expenses] == [
        ("Dinner", 1200, "Mohit"),
        ("Cab", 300, "Rahul"),
    ]


def test_uneven_amount_splits_without_losing_paise(client, trip):
    body = add_expense(client, trip, "Mohit", 100).json()
    assert [s["amount"] for s in body["splits"]] == [33.34, 33.33, 33.33]
    assert round(sum(s["amount"] for s in body["splits"]), 2) == 100


def test_decimal_amount_is_exact(client, trip):
    body = add_expense(client, trip, "Mohit", 10.1).json()
    assert body["amount"] == 10.1


def test_balances_offset_across_expenses(client, trip):
    add_expense(client, trip, "Mohit", 1200)  # Rahul & Ankit owe Mohit 400 each
    add_expense(client, trip, "Rahul", 300)   # Mohit & Ankit owe Rahul 100 each
    balances = client.get(f"/groups/{trip['group']}/balances").json()
    assert balances == {
        "Rahul": {"owes": {"Mohit": 300}},
        "Ankit": {"owes": {"Mohit": 400, "Rahul": 100}},
    }


def test_balances_empty_when_no_expenses(client, trip):
    assert client.get(f"/groups/{trip['group']}/balances").json() == {}


@pytest.mark.parametrize("amount", [0, -50])
def test_amount_must_be_positive(client, trip, amount):
    assert add_expense(client, trip, "Mohit", amount).status_code == 422


def test_amount_with_too_many_decimals_rejected(client, trip):
    assert add_expense(client, trip, "Mohit", 10.555).status_code == 422


def test_blank_description_rejected(client, trip):
    assert add_expense(client, trip, "Mohit", 100, "  ").status_code == 422


def test_unknown_group(client, trip):
    res = client.post("/expenses", json={"group_id": 99, "paid_by": 1, "amount": 10,
                                         "description": "x"})
    assert res.status_code == 404
    assert client.get("/groups/99/expenses").status_code == 404
    assert client.get("/groups/99/balances").status_code == 404


def test_payer_must_be_group_member(client, trip):
    outsider = client.post("/users", json={"name": "Outsider"}).json()
    res = client.post("/expenses", json={"group_id": trip["group"], "paid_by": outsider["id"],
                                         "amount": 10, "description": "x"})
    assert res.status_code == 400


def test_empty_group_rejected(client):
    group = client.post("/groups", json={"name": "Empty"}).json()
    res = client.post("/expenses", json={"group_id": group["id"], "paid_by": 1, "amount": 10,
                                         "description": "x"})
    assert res.status_code == 400


def test_member_added_later_does_not_change_old_expenses(client, trip):
    add_expense(client, trip, "Mohit", 1200)
    late = client.post("/users", json={"name": "Late"}).json()
    client.post(f"/groups/{trip['group']}/members", json={"user_id": late["id"]})
    balances = client.get(f"/groups/{trip['group']}/balances").json()
    assert "Late" not in balances
    assert balances["Rahul"]["owes"]["Mohit"] == 400
