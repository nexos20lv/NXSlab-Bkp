"""NXS-SEC-012 — no security response headers were sent. Add conservative,
non-breaking defaults (nosniff, frame-deny, no-referrer) via after_request.
(No CSP: the UI relies on inline handlers + CDN assets; see advisory.)
"""


def test_nxs_sec_012_headers_on_public_endpoint(client):
    r = client.get("/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"


def test_nxs_sec_012_headers_on_login(client):
    r = client.get("/login")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
