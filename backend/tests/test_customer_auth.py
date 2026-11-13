def test_customer_registration_rejects_non_object_json(client):
    response = client.post("/api/customer-auth/register", json=[])

    assert response.status_code == 400
    assert response.get_json()["message"] == "A valid JSON object is required."


def test_customer_registration_rejects_short_password(client):
    response = client.post(
        "/api/customer-auth/register",
        json={
            "full_name": "Test Customer",
            "email": "customer@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == "Password must be at least 8 characters."


def test_customer_login_rejects_missing_password(client):
    response = client.post(
        "/api/customer-auth/login",
        json={"email": "customer@example.com"},
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == "Email and password are required."
