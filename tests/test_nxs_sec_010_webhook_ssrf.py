"""NXS-SEC-010 — notify() passed the configured webhook_url straight to
urllib.request.urlopen, which honors file://, ftp://, gopher://, dict://, etc.
That is an SSRF / local-resource primitive. Restrict the scheme to http(s).

urlopen is stubbed so the test makes NO outbound network calls.
"""
import core.backup_core as bc


def test_nxs_sec_010_rejects_non_http_schemes(monkeypatch):
    calls = []
    monkeypatch.setattr(bc.urllib.request, "urlopen",
                        lambda req, timeout=None: calls.append(req))
    for bad in ("file:///etc/passwd", "gopher://h/_", "ftp://h/f",
                "dict://h:11211/stat", "ldap://h/", ""):
        bc.notify(bad, {"event": "x"})
    assert calls == [], f"non-http(s) schemes must not reach urlopen, got {calls}"


def test_nxs_sec_010_allows_http_and_https(monkeypatch):
    calls = []
    monkeypatch.setattr(bc.urllib.request, "urlopen",
                        lambda req, timeout=None: calls.append(getattr(req, "full_url", str(req))))
    bc.notify("http://example.test/hook", {"event": "x"})
    bc.notify("https://example.test/hook", {"event": "x"})
    assert len(calls) == 2, "legitimate http(s) webhooks must still be delivered"
