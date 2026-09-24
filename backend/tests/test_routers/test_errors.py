"""Error responses are JSON {"detail": ...} and never expose internals."""

from types import SimpleNamespace

import pytest
from pymongo.errors import ServerSelectionTimeoutError

import routers.claims as claims_router

ORIGIN = "http://localhost:5173"


def _database_raising(exc: Exception):
    async def _find_one(*args, **kwargs):
        raise exc

    return lambda: SimpleNamespace(claims=SimpleNamespace(find_one=_find_one))


async def test_unexpected_error_is_a_generic_json_500_with_cors(async_client, monkeypatch):
    monkeypatch.setattr(claims_router, "get_database", _database_raising(RuntimeError("secret internal detail")))

    response = await async_client.get("/api/claims/claim-test-001", headers={"Origin": ORIGIN})

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "secret internal detail" not in response.text
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_database_outage_is_503(async_client, monkeypatch):
    monkeypatch.setattr(
        claims_router, "get_database", _database_raising(ServerSelectionTimeoutError("db-host:27017 timed out"))
    )

    response = await async_client.get("/api/claims/claim-test-001")

    assert response.status_code == 503
    assert response.json() == {"detail": "The database is unavailable. Please try again later."}
    assert "db-host" not in response.text


@pytest.mark.parametrize(
    ("header", "value"),
    [
        ("x-content-type-options", "nosniff"),
        ("x-frame-options", "DENY"),
        ("referrer-policy", "strict-origin-when-cross-origin"),
    ],
)
async def test_security_headers_on_normal_responses(async_client, header, value):
    response = await async_client.get("/api/health")
    assert response.headers[header] == value


async def test_not_found_uses_detail_shape(async_client):
    response = await async_client.get("/api/claims/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Claim not found"}
