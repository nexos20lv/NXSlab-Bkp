"""Authentification — décorateurs et routes /login /logout /"""
import time
from threading import Lock
from functools import wraps
from flask import Blueprint, session, request, jsonify, redirect, url_for, render_template, make_response
from core.config import load_config, save_config
from core.helpers import verify_pw, hash_pw

auth_bp = Blueprint('auth', __name__)

# ─── NXS-SEC-009: in-process login throttle (no extra dependency) ─────────────
# Keyed on (client address, username) so brute force against one account from a
# source is locked for a window, without a reverse-proxy "single IP -> global
# lockout" effect. NOTE for deployers: behind a proxy, configure real client IP
# (e.g. Werkzeug ProxyFix) so the address component is meaningful.
LOGIN_MAX_FAILS = 5
LOGIN_WINDOW    = 300  # seconds
_LOGIN_ATTEMPTS = {}
_LOGIN_LOCK     = Lock()


def _login_key():
    data = request.get_json(silent=True) or request.form or {}
    return (request.remote_addr or 'unknown', (data.get('username') or '').strip())


def _login_rate_limited(key):
    now = time.time()
    with _LOGIN_LOCK:
        recent = [t for t in _LOGIN_ATTEMPTS.get(key, []) if now - t < LOGIN_WINDOW]
        _LOGIN_ATTEMPTS[key] = recent
        return len(recent) >= LOGIN_MAX_FAILS


def _login_note(key, success):
    with _LOGIN_LOCK:
        if success:
            _LOGIN_ATTEMPTS.pop(key, None)
        else:
            _LOGIN_ATTEMPTS.setdefault(key, []).append(time.time())


def reset_login_throttle():
    """Clear all recorded attempts (used by tests)."""
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.clear()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            if request.is_json or request.path.startswith('/api/') or request.path.startswith('/ws/'):
                return jsonify({'error': 'Non autorisé'}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Non autorisé'}), 401
        role = session.get('role')
        if role is None:
            c        = load_config()
            username = session.get('user', '')
            u        = next((u for u in c.get('users', []) if u.get('username') == username), None)
            # NXS-SEC-005: fail closed — an unknown user or a record without an
            # explicit role must NOT be treated as admin.
            role     = u.get('role', 'readonly') if u else 'readonly'
            session['role'] = role
        if role != 'admin':
            return jsonify({'error': 'Droits administrateur requis'}), 403
        return f(*args, **kwargs)
    return wrapper


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        rl_key = _login_key()
        if _login_rate_limited(rl_key):  # NXS-SEC-009
            msg  = 'Trop de tentatives. Réessayez plus tard.'
            body = jsonify({'error': msg}) if request.is_json \
                   else render_template('login.html', error=msg)
            resp = make_response(body, 429)
            resp.headers['Retry-After'] = str(LOGIN_WINDOW)
            return resp
        data     = request.get_json() or request.form
        c        = load_config()
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        for u in c.get('users', []):
            if u.get('username') != username:
                continue
            ok, needs_upgrade = verify_pw(password, u.get('password_hash', ''))
            if not ok:
                break
            if needs_upgrade:  # NXS-SEC-006: transparently rehash legacy SHA-256
                try:
                    u['password_hash'] = hash_pw(password)
                    save_config(c)
                except Exception:
                    pass
            _login_note(rl_key, success=True)
            session.permanent    = True
            session['logged_in'] = True
            session['user']      = username
            session['role']      = u.get('role', 'readonly')
            payload = {'ok': True, 'role': session['role']}
            return jsonify(payload) if request.is_json else redirect(url_for('auth.index'))
        _login_note(rl_key, success=False)
        return (jsonify({'error': 'Identifiants incorrects'}), 401) if request.is_json \
               else render_template('login.html', error='Identifiants incorrects')
    if session.get('logged_in'):
        return redirect(url_for('auth.index'))
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


@auth_bp.route('/')
@login_required
def index():
    return render_template('index.html')