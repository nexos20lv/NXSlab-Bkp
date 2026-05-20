#!/usr/bin/env python3
"""NXSlab Backup WebUI — point d'entrée"""
import os
import time
import secrets
from flask import Flask

from core.config import load_config

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 * 1024

cfg = load_config()
app.secret_key = cfg.get('secret_key', secrets.token_hex(32))

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
