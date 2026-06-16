"""NXS-SEC-006 — passwords were stored as unsalted single-round SHA-256 and
compared with `==`. Move to a salted slow KDF (Werkzeug pbkdf2-sha256, already a
Flask dependency — no new package), keep backward-compatible verification of
legacy SHA-256 hashes (constant-time), and transparently upgrade them on login.
"""
import re
import json
import hashlib
from core.helpers import hash_pw, verify_pw
from conftest import write_config, login, _CONFIG_FILE

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def test_nxs_sec_006_hash_is_salted_and_slow():
    h1 = hash_pw("correct horse battery staple")
    h2 = hash_pw("correct horse battery staple")
    assert not _HEX64.match(h1), "must not be bare SHA-256 anymore"
    assert h1 != h2, "must be salted (distinct hashes for same password)"
    assert h1.startswith("pbkdf2:"), f"expected pbkdf2 KDF, got {h1[:12]!r}"


def test_nxs_sec_006_verify_roundtrip():
    h = hash_pw("s3cret-pw")
    assert verify_pw("s3cret-pw", h)[0] is True
    assert verify_pw("wrong", h)[0] is False


def test_nxs_sec_006_legacy_sha256_still_verifies_and_flags_upgrade():
    legacy = hashlib.sha256(b"adminpass123").hexdigest()
    ok, needs_upgrade = verify_pw("adminpass123", legacy)
    assert ok is True and needs_upgrade is True
    bad, _ = verify_pw("nope", legacy)
    assert bad is False


def test_nxs_sec_006_login_upgrades_legacy_hash(client):
    # conftest seeds legacy SHA-256 hashes; logging in must succeed AND rewrite
    # the stored hash to the new salted format.
    write_config()
    with open(_CONFIG_FILE) as f:
        before = json.load(f)
    assert _HEX64.match(before["users"][0]["password_hash"])
    r = login(client, "admin", "adminpass123")
    assert r.status_code == 200
    with open(_CONFIG_FILE) as f:
        after = json.load(f)
    stored = after["users"][0]["password_hash"]
    assert not _HEX64.match(stored), "legacy hash must be upgraded after login"
    assert stored.startswith("pbkdf2:")


def test_nxs_sec_006_wrong_password_rejected(client):
    write_config()
    assert login(client, "admin", "WRONG").status_code == 401
