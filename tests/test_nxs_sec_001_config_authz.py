"""NXS-SEC-001 — readonly users must not be able to rewrite system service
configs (/etc/samba/smb.conf, /etc/vsftpd.conf). The write (POST) path must be
admin-only, consistent with every other samba/ftp mutation route.

The authorization check must happen BEFORE any filesystem access, so this test
is OS-independent (it never depends on /etc files existing).
"""
from conftest import login


def test_nxs_sec_001_readonly_cannot_write_samba_config(readonly_client):
    r = readonly_client.post("/api/samba/config", json={"content": "[global]\n"})
    assert r.status_code == 403, f"readonly must be forbidden, got {r.status_code}"


def test_nxs_sec_001_readonly_cannot_write_ftp_config(readonly_client):
    r = readonly_client.post("/api/ftp/config", json={"content": "listen=YES\n"})
    assert r.status_code == 403, f"readonly must be forbidden, got {r.status_code}"


def test_nxs_sec_001_unauth_cannot_write_config(client):
    assert client.post("/api/samba/config", json={"content": "x"}).status_code == 401
    assert client.post("/api/ftp/config", json={"content": "x"}).status_code == 401


def test_nxs_sec_001_admin_passes_authz_gate(admin_client):
    # Admin must NOT be blocked by authz (the later file op may fail on a test
    # box without /etc/samba, but that is 4xx/5xx other than 403, never 403).
    r = admin_client.post("/api/samba/config", json={"content": "[global]\n"})
    assert r.status_code != 403, "admin must pass the authz gate"
    r = admin_client.post("/api/ftp/config", json={"content": "listen=YES\n"})
    assert r.status_code != 403, "admin must pass the authz gate"


def test_nxs_sec_001_readonly_can_still_read_config(readonly_client):
    # Read (GET) stays available to any logged-in user — behavior preserved.
    r = readonly_client.get("/api/samba/config")
    assert r.status_code != 403, "readonly should still be able to GET (read) config"
