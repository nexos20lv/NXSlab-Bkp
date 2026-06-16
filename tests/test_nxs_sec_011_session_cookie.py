"""NXS-SEC-011 — the session cookie set no SameSite attribute (CSRF surface)
and no explicit hardening. Set SameSite=Lax + HttpOnly, make Secure configurable
(default off so HTTP installs keep working), and give the session a finite
lifetime.
"""
from datetime import timedelta
from conftest import login


def test_nxs_sec_011_set_cookie_has_samesite_and_httponly(client):
    r = login(client, "admin", "adminpass123")
    sc = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in sc, sc
    assert "SameSite=Lax" in sc, sc


def test_nxs_sec_011_config_flags(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert "SESSION_COOKIE_SECURE" in app.config  # present + configurable
    assert isinstance(app.config["PERMANENT_SESSION_LIFETIME"], timedelta)
    assert app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() > 0
