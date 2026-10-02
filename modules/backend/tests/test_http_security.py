from fastapi.testclient import TestClient

from src.main import app


def test_cors_allows_configured_localhost_and_rejects_other_origins():
    with TestClient(app) as client:
        allowed = client.options(
            "/auth/login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        denied = client.options(
            "/auth/login",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers


def test_security_headers_and_no_store_are_set():
    with TestClient(app) as client:
        response = client.get("/auth/config")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_validation_errors_never_echo_rejected_passwords_or_guest_proof():
    with TestClient(app) as client:
        for route, body, forbidden in [
            ("/auth/signup", {"username": "synthetic", "email": "synthetic@example.test", "password": "x" * 300}, "x" * 300),
            ("/guest/claim", {"guest_token": ["synthetic-private-proof"]}, "synthetic-private-proof"),
        ]:
            response = client.post(route, json=body)
            # Claim authentication may reject before body validation, also safe.
            assert response.status_code in {401, 422}
            assert forbidden not in response.text
            assert '"input"' not in response.text
