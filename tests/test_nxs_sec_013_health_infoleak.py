"""NXS-SEC-013 — the unauthenticated /health endpoint disclosed every remote's
hostname/name and backup status (recon of internal infrastructure). Trim the
public response to non-sensitive liveness + capability flags; expose per-remote
details only to an authenticated session. The frontend only consumes version /
uptime / has_* from /health, so this is behavior-preserving for the UI.
"""
import json


def test_nxs_sec_013_unauth_health_hides_remote_hosts(client):
    j = client.get("/health").get_json()
    assert "remotes" not in j, "unauthenticated /health must not enumerate remotes"
    assert "203.0.113.9" not in json.dumps(j), "remote host must not leak anywhere in payload"
    # liveness / capability info preserved for monitoring + the settings UI
    assert j.get("status") == "ok"
    assert {"version", "uptime_seconds", "has_paramiko", "has_websocket"} <= set(j)


def test_nxs_sec_013_authed_health_still_has_remote_details(admin_client):
    j = admin_client.get("/health").get_json()
    assert "remotes" in j
    assert any(r.get("host") == "203.0.113.9" for r in j["remotes"])
