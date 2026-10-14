import pytest


@pytest.fixture
def trip(client):
    group = client.post("/groups", json={"name": "Goa Trip"}).json()
    ids = {}
    for name in ("Mohit", "Rahul", "Ankit"):
        user = client.post("/users", json={"name": name}).json()
        client.post(f"/groups/{group['id']}/members", json={"user_id": user["id"]})
        ids[name] = user["id"]
    return {"group": group["id"], **ids}


def add_expense(client, trip, payer, amount):
    res = client.post("/expenses", json={"group_id": trip["group"], "paid_by": trip[payer],
                                         "amount": amount, "description": "x"})
    assert res.status_code == 201


def settle(client, trip, payer, receiver, amount):
    return client.post(
        f"/groups/{trip['group']}/settlements",
        json={"from_user": trip[payer], "to_user": trip[receiver], "amount": amount},
    )


def balances(client, trip):
    return client.get(f"/groups/{trip['group']}/balances").json()


def suggested(client, trip):
    return client.get(f"/groups/{trip['group']}/settlements/suggested").json()


def test_settlement_clears_debt(client, trip):
    add_expense(client, trip, "Mohit", 1200)
    res = settle(client, trip, "Rahul", "Mohit", 400)
    assert res.status_code == 201
    assert res.json()["from_user"] == "Rahul" and res.json()["amount"] == 400
    assert balances(client, trip) == {"Ankit": {"owes": {"Mohit": 400}}}


def test_partial_settlement(client, trip):
    add_expense(client, trip, "Mohit", 1200)
    settle(client, trip, "Rahul", "Mohit", 150)
    assert balances(client, trip)["Rahul"] == {"owes": {"Mohit": 250}}


def test_settlement_validation(client, trip):
    assert settle(client, trip, "Rahul", "Rahul", 10).status_code == 400
    assert settle(client, trip, "Rahul", "Mohit", 0).status_code == 422
    assert settle(client, trip, "Rahul", "Mohit", -5).status_code == 422
    outsider = client.post("/users", json={"name": "Outsider"}).json()
    res = client.post(f"/groups/{trip['group']}/settlements",
                      json={"from_user": outsider["id"], "to_user": trip["Mohit"], "amount": 10})
    assert res.status_code == 400
    res = client.post("/groups/99/settlements", json={"from_user": 1, "to_user": 2, "amount": 10})
    assert res.status_code == 404


def test_suggestions_spec_example(client, trip):
    add_expense(client, trip, "Mohit", 1200)
    assert suggested(client, trip) == [
        {"from_user": "Rahul", "to_user": "Mohit", "amount": 400},
        {"from_user": "Ankit", "to_user": "Mohit", "amount": 400},
    ]


def test_suggestions_empty_without_expenses_or_when_settled(client, trip):
    assert suggested(client, trip) == []
    add_expense(client, trip, "Mohit", 1200)
    settle(client, trip, "Rahul", "Mohit", 400)
    settle(client, trip, "Ankit", "Mohit", 400)
    assert suggested(client, trip) == []
    assert balances(client, trip) == {}


def test_suggestions_beat_pairwise_and_clear_everything(client, trip):
    add_expense(client, trip, "Mohit", 300)  # Rahul, Ankit owe Mohit 100 each
    add_expense(client, trip, "Rahul", 600)  # Mohit, Ankit owe Rahul 200 each
    # Pairwise: Mohit owes Rahul 100, Ankit owes Mohit 100, Ankit owes Rahul 200 -> 3 debts.
    assert sum(len(v["owes"]) for v in balances(client, trip).values()) == 3
    plan = suggested(client, trip)
    assert plan == [{"from_user": "Ankit", "to_user": "Rahul", "amount": 300}]
    # Following the plan leaves nothing to suggest.
    settle(client, trip, "Ankit", "Rahul", 300)
    assert suggested(client, trip) == []


def test_simplified_balances_remove_cycle(client, trip):
    add_expense(client, trip, "Mohit", 300)
    add_expense(client, trip, "Rahul", 600)
    url = f"/groups/{trip['group']}/balances?simplify=true"
    assert client.get(url).json() == {"Ankit": {"owes": {"Rahul": 300}}}

    settle(client, trip, "Ankit", "Rahul", 300)
    # Pairwise view shows a cycle (nobody is really owed anything); simplified view is clean.
    assert len(balances(client, trip)) == 3
    assert client.get(url).json() == {}


def test_simplified_matches_pairwise_for_spec_example(client, trip):
    add_expense(client, trip, "Mohit", 1200)
    simplified = client.get(f"/groups/{trip['group']}/balances?simplify=true").json()
    assert simplified == balances(client, trip)
