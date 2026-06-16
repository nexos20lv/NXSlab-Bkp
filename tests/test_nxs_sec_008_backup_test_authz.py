"""NXS-SEC-008 — /api/backup/test was @login_required, so any logged-in user
(incl. readonly) could make the server open an SSH connection to an
attacker-supplied host, with an attacker-supplied key_path (arbitrary local key
file) or password. It must be admin-only, consistent with run/restore/settings.

ssh_connect is stubbed so the test performs NO outbound network (safety rail);
it also proves admin reaches the handler while readonly/anon are blocked first.
"""
import blueprints.backup as backup_mod


def _blocked(remote):
    raise RuntimeError("network blocked in test")


def test_nxs_sec_008_readonly_denied(readonly_client, monkeypatch):
    monkeypatch.setattr(backup_mod, "ssh_connect", _blocked)
    r = readonly_client.post("/api/backup/test/abcd1234", json={"host": "10.0.0.1"})
    assert r.status_code == 403


def test_nxs_sec_008_unauth_denied(client, monkeypatch):
    monkeypatch.setattr(backup_mod, "ssh_connect", _blocked)
    r = client.post("/api/backup/test/abcd1234", json={"host": "10.0.0.1"})
    assert r.status_code == 401


def test_nxs_sec_008_admin_passes_gate(admin_client, monkeypatch):
    calls = {}
    def _stub(remote):
        calls["reached"] = True
        raise RuntimeError("network blocked in test")
    monkeypatch.setattr(backup_mod, "ssh_connect", _stub)
    r = admin_client.post("/api/backup/test/abcd1234", json={})
    assert r.status_code != 403, "admin must pass the authorization gate"
    assert calls.get("reached") is True, "handler should run for admin (no outbound; stubbed)"
