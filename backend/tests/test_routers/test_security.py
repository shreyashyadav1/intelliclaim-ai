"""Rate limits, proxy-aware client IPs and the optional admin key."""

from types import SimpleNamespace

import pytest

from config import settings
from security import client_ip

ADMIN_KEY = "test-admin-key-123"


# --- Client IP ------------------------------------------------------------------------


def _request(forwarded: str | None, peer: str = "10.0.0.1"):
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))


@pytest.mark.parametrize(
    ("hops", "forwarded", "expected"),
    [
        (0, "1.1.1.1", "10.0.0.1"),  # no proxy: the header is client-controlled and ignored
        (1, None, "10.0.0.1"),
        (1, "1.1.1.1", "1.1.1.1"),
        (1, "6.6.6.6, 1.1.1.1", "1.1.1.1"),  # a spoofed entry on the left is ignored
        (2, "6.6.6.6, 1.1.1.1, 172.16.0.2", "1.1.1.1"),
        (3, "1.1.1.1", "1.1.1.1"),  # fewer entries than hops: take the leftmost
    ],
)
def test_client_ip(monkeypatch, hops, forwarded, expected):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", hops)
    assert client_ip(_request(forwarded)) == expected


# --- Rate limits ------------------------------------------------------------------------


async def test_rate_limit_returns_429_in_the_api_error_shape(async_client, rate_limits):
    for _ in range(5):  # GET /api/health/groq allows 5 per minute
        assert (await async_client.get("/api/health/groq")).status_code == 503

    response = await async_client.get("/api/health/groq")

    assert response.status_code == 429
    assert response.json() == {"detail": "Too many requests (5 per 1 minute). Please try again later."}
    assert response.headers["retry-after"] == "60"


async def test_rate_limits_are_per_client_behind_the_proxy(async_client, rate_limits):
    alice = {"X-Forwarded-For": "203.0.113.10"}
    bob = {"X-Forwarded-For": "203.0.113.20"}
    for _ in range(5):
        await async_client.get("/api/health/groq", headers=alice)

    assert (await async_client.get("/api/health/groq", headers=alice)).status_code == 429
    assert (await async_client.get("/api/health/groq", headers=bob)).status_code == 503
    # Prepending a fake address does not give Alice a new bucket.
    spoofed = {"X-Forwarded-For": "198.51.100.1, 203.0.113.10"}
    assert (await async_client.get("/api/health/groq", headers=spoofed)).status_code == 429


async def test_path_parameters_share_one_bucket(async_client, rate_limits):
    """Validating claim-a, claim-b, ... must not open a fresh bucket per claim."""
    for index in range(10):  # POST /api/validate/{id} allows 10 per minute
        assert (await async_client.post(f"/api/validate/missing-{index}")).status_code == 404
    assert (await async_client.post("/api/validate/missing-10")).status_code == 429


async def test_read_endpoints_are_not_rate_limited(async_client, rate_limits):
    for _ in range(40):
        assert (await async_client.get("/api/claims")).status_code == 200


# --- Admin key ---------------------------------------------------------------------------


PROTECTED = [
    ("delete", "/api/documents/doc-test-001"),
    ("delete", "/api/claims/claim-test-001"),
    ("post", "/api/rag/index-all"),
    ("get", "/api/health/groq"),
]


@pytest.fixture
def admin_key(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", ADMIN_KEY)


@pytest.mark.parametrize(("method", "path"), PROTECTED)
async def test_protected_endpoints_need_the_admin_key(async_client, test_db, admin_key, method, path):
    missing = await async_client.request(method.upper(), path)
    wrong = await async_client.request(method.upper(), path, headers={"X-Admin-Key": "wrong"})

    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == {"detail": "Missing or invalid X-Admin-Key header"}
    assert await test_db.documents.count_documents({}) == 2
    assert await test_db.claims.count_documents({}) == 2


@pytest.mark.parametrize(("method", "path"), PROTECTED)
async def test_the_right_admin_key_is_accepted(async_client, admin_key, method, path):
    response = await async_client.request(method.upper(), path, headers={"X-Admin-Key": ADMIN_KEY})
    assert response.status_code != 401


@pytest.mark.parametrize(("method", "path"), PROTECTED)
async def test_without_admin_key_configured_nothing_is_required(async_client, method, path):
    response = await async_client.request(method.upper(), path)
    assert response.status_code != 401


async def test_other_endpoints_do_not_need_the_admin_key(async_client, admin_key):
    assert (await async_client.put("/api/claims/claim-test-001", json={"status": "approved"})).status_code == 200
    assert (await async_client.get("/api/documents")).status_code == 200
