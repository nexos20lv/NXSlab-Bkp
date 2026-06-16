"""NXS-SEC-004 — passwords for system (Samba/FTP) users are piped to the
line-oriented tools chpasswd/smbpasswd via stdin as "user:password\\n". The
password was only length-checked, so a newline let an admin inject extra
chpasswd lines, e.g. password "x\\nroot:pwned" -> also sets root's password.
That crosses the web-admin -> host-root boundary. Control chars must be rejected.
"""
from core.helpers import valid_secret


def test_nxs_sec_004_valid_secret_rejects_control_chars():
    assert valid_secret("Str0ng-Pass_42") is True
    assert valid_secret("x\nroot:pwned") is False     # newline injection
    assert valid_secret("x\r\nroot:pwned") is False    # CRLF
    assert valid_secret("a\x00b") is False             # NUL
    assert valid_secret("tab\there") is False          # other C0 control


def test_nxs_sec_004_ftp_add_rejects_newline_password(admin_client):
    r = admin_client.post("/api/ftp/users/add",
                          json={"username": "ftpuser", "password": "abc\nroot:pwned"})
    assert r.status_code == 400


def test_nxs_sec_004_ftp_passwd_rejects_newline_password(admin_client):
    r = admin_client.post("/api/ftp/users/passwd",
                          json={"username": "ftpuser", "password": "abc\nroot:pwned"})
    assert r.status_code == 400


def test_nxs_sec_004_samba_add_rejects_newline_password(admin_client):
    r = admin_client.post("/api/samba/users/add",
                          json={"username": "smbuser", "password": "abc\nroot:pwned"})
    assert r.status_code == 400


def test_nxs_sec_004_samba_passwd_rejects_newline_password(admin_client):
    r = admin_client.post("/api/samba/users/passwd",
                          json={"username": "smbuser", "password": "abc\nroot:pwned"})
    assert r.status_code == 400
