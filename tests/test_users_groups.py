def make_user(client, name):
    return client.post("/users", json={"name": name}).json()


def make_group(client, name="Goa Trip"):
    return client.post("/groups", json={"name": name}).json()


def test_create_and_list_users(client):
    res = client.post("/users", json={"name": "Mohit"})
    assert res.status_code == 201
    assert res.json() == {"id": 1, "name": "Mohit"}
    make_user(client, "Rahul")
    assert [u["name"] for u in client.get("/users").json()] == ["Mohit", "Rahul"]


def test_duplicate_user_name_rejected(client):
    make_user(client, "Mohit")
    assert client.post("/users", json={"name": "Mohit"}).status_code == 409


def test_blank_user_name_rejected(client):
    assert client.post("/users", json={"name": "   "}).status_code == 422


def test_create_group(client):
    res = client.post("/groups", json={"name": "Goa Trip"})
    assert res.status_code == 201
    assert res.json() == {"id": 1, "name": "Goa Trip"}


def test_add_and_list_members(client):
    mohit, rahul = make_user(client, "Mohit"), make_user(client, "Rahul")
    group = make_group(client)
    for user in (mohit, rahul):
        res = client.post(f"/groups/{group['id']}/members", json={"user_id": user["id"]})
        assert res.status_code == 201
    members = client.get(f"/groups/{group['id']}/members").json()
    assert [m["name"] for m in members] == ["Mohit", "Rahul"]


def test_add_member_errors(client):
    user = make_user(client, "Mohit")
    group = make_group(client)
    url = f"/groups/{group['id']}/members"
    assert client.post(url, json={"user_id": user["id"]}).status_code == 201
    assert client.post(url, json={"user_id": user["id"]}).status_code == 409  # duplicate
    assert client.post(url, json={"user_id": 999}).status_code == 404  # no such user
    assert client.post("/groups/999/members", json={"user_id": user["id"]}).status_code == 404
    assert client.get("/groups/999/members").status_code == 404
