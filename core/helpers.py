"""Fonctions utilitaires partagées."""
import re, subprocess, hashlib, hmac
from werkzeug.security import generate_password_hash, check_password_hash

_LEGACY_SHA256 = re.compile(r'^[0-9a-f]{64}$')


def hash_pw(pw: str) -> str:
    # NXS-SEC-006: salted slow KDF (pbkdf2-sha256 via Werkzeug, already a Flask
    # dependency) instead of the previous unsalted single-round SHA-256.
    return generate_password_hash(pw, method='pbkdf2:sha256')


def verify_pw(pw: str, stored: str):
    """Return (ok, needs_upgrade). Verifies against the new salted format and,
    for backward compatibility, legacy unsalted SHA-256 hashes (constant-time).
    A successful legacy match sets needs_upgrade so the caller can rehash and
    persist the modern format (NXS-SEC-006)."""
    stored = stored or ''
    if _LEGACY_SHA256.match(stored):
        ok = hmac.compare_digest(hashlib.sha256(pw.encode()).hexdigest(), stored)
        return ok, ok
    try:
        return check_password_hash(stored, pw), False
    except Exception:
        return False, False


def valid_username(u: str) -> bool:
    return bool(re.match(r'^[a-z_][a-z0-9_.-]{0,30}$', u))


def valid_secret(s: str) -> bool:
    """Reject control characters (newline/CR/NUL/...) in values piped via stdin
    to line-oriented tools such as chpasswd/smbpasswd. A newline in a password
    would otherwise smuggle an extra 'user:password' line into chpasswd and let
    a caller set arbitrary system accounts' passwords (NXS-SEC-004)."""
    return isinstance(s, str) and not any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in s)


def run(args: list, stdin: str = None, timeout: int = 15):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, input=stdin)
        return {'ok': r.returncode == 0, 'out': r.stdout, 'err': r.stderr, 'rc': r.returncode}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'out': '', 'err': 'Timeout', 'rc': -1}
    except Exception as e:
        return {'ok': False, 'out': '', 'err': str(e), 'rc': -1}


def shell(cmd: str, timeout: int = 15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {'ok': r.returncode == 0, 'out': r.stdout, 'err': r.stderr, 'rc': r.returncode}
    except Exception as e:
        return {'ok': False, 'out': '', 'err': str(e), 'rc': -1}


def svc_state(name: str) -> str:
    r = run(['systemctl', 'is-active', name])
    s = r['out'].strip()
    return {'active': 'up', 'inactive': 'inactive', 'failed': 'failed'}.get(s, 'down')


def setup_data_access(username: str) -> None:
    from core.config import get_data_dir
    data_dir = get_data_dir()
    run(['groupadd',  '-f',  'nxslab-data'])
    run(['chgrp',  'nxslab-data', data_dir])
    run(['chmod',  '2775',        data_dir])
    run(['usermod', '-a', '-G', 'nxslab-data', username])


def human_size(n):
    n = float(n)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(n) < 1024.0 or unit == 'TB':
            return f"{int(n)} B" if unit == 'B' else f"{n:.1f} {unit}"
        n /= 1024.0