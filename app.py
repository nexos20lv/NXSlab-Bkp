#!/usr/bin/env python3
"""NXSlab Backup WebUI — point d'entrée"""
import os
import time
import secrets
from datetime import timedelta
from flask import Flask

from core.config import load_config

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 * 1024

cfg = load_config()
app.secret_key = cfg.get('secret_key', secrets.token_hex(32))

def _cfg_bool(v, default=False):
    # Robust truthy parse so a JSON string like "false"/"0" is not treated as
    # True (which bool("false") would do and break HTTP logins).
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ('1', 'true', 'yes', 'on')
    return default


def _cfg_int(v, default, minimum=1):
    # Safe parse so a bad config value (e.g. "12h") can't crash startup.
    try:
        return max(minimum, int(v))
    except (TypeError, ValueError):
        return default


# NXS-SEC-011: harden the session cookie. SameSite=Lax mitigates CSRF on the
# state-changing POST API; HttpOnly keeps it out of JS. Secure is configurable
# (default off so plain-HTTP installs keep working) — set "cookie_secure": true
# in config.json when serving over HTTPS. The session also gets a finite lifetime.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=_cfg_bool(cfg.get('cookie_secure', False)),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=_cfg_int(cfg.get('session_hours', 12), 12)),
)


@app.after_request
def _security_headers(resp):
    # NXS-SEC-012: conservative, non-breaking defense-in-depth headers. No CSP
    # here — the UI relies on inline event handlers and CDN assets, so a useful
    # CSP needs a handler refactor first (tracked as a recommendation).
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    resp.headers.setdefault('Referrer-Policy', 'no-referrer')
    return resp

_STATIC_VER = str(int(time.time()))

@app.context_processor
def _inject_static_ver():
    return dict(sv=_STATIC_VER)

# ─── WebSocket (optionnel) ────────────────────────────────────────────────────

try:
    from flask_sock import Sock
    sock = Sock(app)
    app.config['HAS_SOCK'] = True
    from core.terminal import register_terminal
    register_terminal(sock)
except ImportError:
    app.config['HAS_SOCK'] = False

# ─── Blueprints ───────────────────────────────────────────────────────────────

from blueprints.auth import auth_bp
from blueprints.system import system_bp
from blueprints.samba import samba_bp
from blueprints.ftp import ftp_bp
from blueprints.files import files_bp
from blueprints.users import users_bp
from blueprints.remotes import remotes_bp
from blueprints.backup import backup_bp

for bp in (auth_bp, system_bp, samba_bp, ftp_bp, files_bp, users_bp, remotes_bp, backup_bp):
    app.register_blueprint(bp)

# ─── Scheduler ────────────────────────────────────────────────────────────────

from core.backup_core import apply_schedule
apply_schedule()

# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    c    = load_config()
    port = int(os.environ.get('PORT', c.get('port', 5080)))
    app.run(host='::', port=port, debug=False, threaded=True)
