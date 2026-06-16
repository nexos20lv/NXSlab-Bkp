"""NXS-SEC-009 — /login had no rate limiting, allowing unthrottled online
brute force. Add an in-process throttle (no new dependency) keyed on
(remote_addr, username) so repeated failures lock that account from that source
for a window, while a correct password for a different account is unaffected
(avoids a reverse-proxy "single IP -> global lockout" footgun).
"""
import blueprints.auth as auth_mod
from conftest import login


def test_nxs_sec_009_lockout_after_repeated_failures(client):
    auth_mod.reset_login_throttle()
    for _ in range(auth_mod.LOGIN_MAX_FAILS):
        assert login(client, "admin", "WRONG").status_code == 401
    # further attempts are blocked, even with the correct password
    r = login(client, "admin", "adminpass123")
    assert r.status_code == 429
    assert r.headers.get("Retry-After")


def test_nxs_sec_009_other_account_not_locked(client):
    auth_mod.reset_login_throttle()
    for _ in range(auth_mod.LOGIN_MAX_FAILS):
        login(client, "admin", "WRONG")
    # a different account is keyed separately -> not collateral-locked
    assert login(client, "viewer", "viewerpass123").status_code == 200


def test_nxs_sec_009_correct_login_not_throttled(client):
    auth_mod.reset_login_throttle()
    assert login(client, "admin", "adminpass123").status_code == 200


def test_nxs_sec_009_throttle_prunes_stale_keys():
    # Stale keys (older than the window) must be pruned so the table can't grow
    # without bound under sustained attack.
    import time
    auth_mod.reset_login_throttle()
    auth_mod._LOGIN_ATTEMPTS[("203.0.113.1", "ghost")] = [time.time() - auth_mod.LOGIN_WINDOW - 10]
    auth_mod._login_rate_limited(("203.0.113.2", "other"))
    assert ("203.0.113.1", "ghost") not in auth_mod._LOGIN_ATTEMPTS
