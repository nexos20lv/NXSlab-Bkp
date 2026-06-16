"""NXS-SEC-002 — the state-changing file-manager routes (upload/mkdir/delete/
rename) were only @login_required, letting a readonly account create, overwrite,
rename and delete data under DATA_DIR (which holds backups, i.e. dumped secrets).
They must be admin-only. Read paths (list/download) stay open to readonly.
"""
import os
from conftest import DATA_DIR


def _mkdir(rel):
    full = os.path.join(DATA_DIR, rel)
    os.makedirs(full, exist_ok=True)
    return full


def test_nxs_sec_002_readonly_cannot_mkdir(readonly_client):
    r = readonly_client.post("/api/files/mkdir", json={"path": "/", "name": "evil_dir"})
    assert r.status_code == 403


def test_nxs_sec_002_readonly_cannot_upload(readonly_client):
    r = readonly_client.post("/api/files/upload?path=/")
    assert r.status_code == 403


def test_nxs_sec_002_readonly_cannot_delete(readonly_client):
    _mkdir("todelete")
    r = readonly_client.post("/api/files/delete", json={"path": "/todelete"})
    assert r.status_code == 403
    assert os.path.isdir(os.path.join(DATA_DIR, "todelete")), "must not have been deleted"


def test_nxs_sec_002_readonly_cannot_rename(readonly_client):
    _mkdir("torename")
    r = readonly_client.post("/api/files/rename", json={"path": "/torename", "name": "renamed"})
    assert r.status_code == 403


def test_nxs_sec_002_unauth_blocked(client):
    assert client.post("/api/files/mkdir", json={"path": "/", "name": "x"}).status_code == 401


def test_nxs_sec_002_readonly_can_still_list(readonly_client):
    assert readonly_client.get("/api/files/list?path=/").status_code == 200


def test_nxs_sec_002_admin_can_mkdir(admin_client):
    r = admin_client.post("/api/files/mkdir", json={"path": "/", "name": "admin_made"})
    assert r.status_code == 200 and r.get_json().get("ok") is True
