def test_welcome(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json() == {
        "message": "Welcome to the Expense Sharing Service",
        "docs": "/docs",
        "health": "/health",
    }


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
