"""NXS-SEC-005 — admin_required resolved a missing/unknown role to 'admin'
(fail-open): `role = u.get('role', 'admin') if u else 'admin'`. A session that
is logged in but whose role cannot be resolved (user removed from config, or a
user record with no 'role' key) was therefore treated as admin. Authorization
must fail closed (least privilege). /api/users is an @admin_required route.
"""
from conftest import write_config


def test_nxs_sec_005_unknown_user_denied(client):
    # logged-in session whose user no longer exists in config
    with client.session_transaction() as s:
        s["logged_in"] = True
        s["user"] = "ghost-not-in-config"
    assert client.get("/api/users").status_code == 403


def test_nxs_sec_005_roleless_user_denied(client):
    write_config(users=[{"username": "norole", "password_hash": "x"}])  # no 'role' key
    with client.session_transaction() as s:
        s["logged_in"] = True
        s["user"] = "norole"
    assert client.get("/api/users").status_code == 403


def test_nxs_sec_005_real_admin_still_allowed(admin_client):
    assert admin_client.get("/api/users").status_code == 200
