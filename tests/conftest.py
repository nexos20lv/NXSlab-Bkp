"""Security regression test harness.

Runs entirely against a LOCAL, disposable Flask ``test_client`` (no sockets, no
outbound network). A throwaway config with DUMMY values and a temp DATA_DIR are
created before the app is imported; nothing touches a real install or real
credentials.
"""
import os
import json
import hashlib
import tempfile
import shutil

import pytest

# ── Throwaway config + temp data dir, wired in BEFORE importing the app ───────
_TMP = tempfile.mkdtemp(prefix="nxslab_test_")
_DATA_DIR = os.path.join(_TMP, "data")
os.makedirs(_DATA_DIR, exist_ok=True)
_CONFIG_FILE = os.path.join(_TMP, "config.json")
os.environ["CONFIG_FILE"] = _CONFIG_FILE

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()


def write_config(users=None, remotes=None, **extra):
    """(Re)write the throwaway config. load_config() re-reads the file each call,
    so tests can reshape the config between requests."""
    if users is None:
        users = [
            {"username": "admin", "password_hash": _sha256("adminpass123"), "role": "admin"},
            {"username": "viewer", "password_hash": _sha256("viewerpass123"), "role": "readonly"},
        ]
    cfg = {
        "users": users,
        "secret_key": "dummy-test-secret-not-a-real-key",
        "port": 5080,
        "data_dir": _DATA_DIR,
        "remotes": remotes if remotes is not None else [
            {"id": "abcd1234", "name": "dummy-vps", "host": "203.0.113.9",
             "user": "root", "auth_type": "password", "password": "dummy",
             "backup": {"subdir": "dummy"}},
        ],
    }
    cfg.update(extra)
    with open(_CONFIG_FILE, "w") as f:
        json.dump(cfg, f)
    return cfg


# Initial config must exist before the app module is imported.
write_config()

import app as appmod  # noqa: E402

DATA_DIR = _DATA_DIR


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture
def app():
    return appmod.app


@pytest.fixture
def client():
    write_config()  # reset to known state for each test
    return appmod.app.test_client()


def login(client, username, password):
    """Authenticate the test client; returns the response."""
    return client.post("/login", json={"username": username, "password": password})


@pytest.fixture
def admin_client():
    write_config()
    c = appmod.app.test_client()
    r = login(c, "admin", "adminpass123")
    assert r.status_code == 200, r.data
    return c


@pytest.fixture
def readonly_client():
    write_config()
    c = appmod.app.test_client()
    r = login(c, "viewer", "viewerpass123")
    assert r.status_code == 200, r.data
    return c
