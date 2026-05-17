"""Authentification — décorateurs et routes /login /logout /"""
from functools import wraps
from flask import Blueprint, session, request, jsonify, redirect, url_for, render_template
from config import load_config
from helpers import hash_pw

auth_bp = Blueprint('auth', __name__)


# ─── Décorateurs ─────────────────────────────────────────────────────────────

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
        if session.get('role') != 'admin':
            return jsonify({'error': 'Droits administrateur requis'}), 403
        return f(*args, **kwargs)
    return wrapper


# ─── Routes ──────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data     = request.get_json() or request.form
        c        = load_config()
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        for u in c.get('users', []):
            if u.get('username') == username and hash_pw(password) == u.get('password_hash', ''):
                session.permanent    = True
                session['logged_in'] = True
                session['user']      = username
                session['role']      = u.get('role', 'readonly')
                payload = {'ok': True, 'role': session['role']}
                return jsonify(payload) if request.is_json else redirect(url_for('auth.index'))
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
