"""NXS-SEC-003 — the web SSH terminal (/ws/terminal/<remote_id>) opens an
interactive shell on the remote VPS using stored credentials. It was gated only
on session['logged_in'], so a readonly account could obtain a remote root shell.
Authorization must require the admin role.

flask-sock WebSocket handshakes cannot be driven through Flask's test_client, so
the security decision is factored into terminal_authorized(session) and asserted
directly here. (Live WebSocket integration is noted as not covered by the harness.)
"""
from core.terminal import terminal_authorized


def test_nxs_sec_003_admin_authorized():
    assert terminal_authorized({"logged_in": True, "role": "admin"}) is True


def test_nxs_sec_003_readonly_denied():
    assert terminal_authorized({"logged_in": True, "role": "readonly"}) is False


def test_nxs_sec_003_logged_in_without_role_denied():
    assert terminal_authorized({"logged_in": True}) is False


def test_nxs_sec_003_anonymous_denied():
    assert terminal_authorized({"logged_in": False, "role": "admin"}) is False
    assert terminal_authorized({}) is False
