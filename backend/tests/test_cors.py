from app import create_app


def test_development_cors_allows_both_local_frontend_hostnames():
    app = create_app()
    client = app.test_client()

    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        response = client.options(
            "/api/businesses",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.headers["Access-Control-Allow-Origin"] == origin


def test_development_cors_does_not_allow_arbitrary_origins():
    app = create_app()
    client = app.test_client()

    response = client.options(
        "/api/businesses",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "Access-Control-Allow-Origin" not in response.headers
