"""Routes gestion utilisateurs WebUI — /api/users/* /api/settings/*"""
import re
from flask import Blueprint, request, jsonify, session
from auth import login_required, admin_required
from config import load_config, save_config
from helpers import hash_pw

users_bp = Blueprint('users', __name__)


@users_bp.route('/api/settings/me')
@login_required
def settings_me():
    return jsonify({'username': session.get('user'), 'role': session.get('role')})


@users_bp.route('/api/settings/password', methods=['POST'])
@login_required
def change_password():
    d        = request.json or {}
    current  = d.get('current', '')
    new_pw   = d.get('new', '')
    username = session.get('user')
    c = load_config()
    for u in c.get('users', []):
        if u.get('username') == username:
            if hash_pw(current) != u['password_hash']:
                return jsonify({'error': 'Mot de passe actuel incorrect'}), 401
            if len(new_pw) < 8:
                return jsonify({'error': 'Le nouveau mot de passe doit faire au moins 8 caractères'}), 400
            u['password_hash'] = hash_pw(new_pw)
            save_config(c)
            return jsonify({'ok': True})
    return jsonify({'error': 'Utilisateur introuvable'}), 404


@users_bp.route('/api/users')
@admin_required
def users_list():
    c = load_config()
    users = [{'username': u['username'], 'role': u.get('role', 'readonly')} for u in c.get('users', [])]
    return jsonify({'users': users})


@users_bp.route('/api/users/add', methods=['POST'])
@admin_required
def users_add():
    d        = request.json or {}
    username = (d.get('username') or '').strip().lower()
    password = d.get('password') or ''
    role     = d.get('role', 'readonly')
    if not re.match(r'^[a-z_][a-z0-9_.-]{0,30}$', username):
        return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if len(password) < 8:                return jsonify({'error': 'Mot de passe trop court (min. 8 car.)'}), 400
    if role not in ('admin', 'readonly'): return jsonify({'error': 'Rôle invalide'}), 400
    c = load_config()
    if any(u['username'] == username for u in c.get('users', [])):
        return jsonify({'error': 'Utilisateur déjà existant'}), 400
    c.setdefault('users', []).append({'username': username, 'password_hash': hash_pw(password), 'role': role})
    save_config(c)
    return jsonify({'ok': True})


@users_bp.route('/api/users/delete', methods=['POST'])
@admin_required
def users_delete():
    username = (request.json or {}).get('username', '').strip()
    if username == session.get('user'):
        return jsonify({'error': 'Impossible de supprimer son propre compte'}), 400
    c = load_config()
    before      = len(c.get('users', []))
    c['users']  = [u for u in c.get('users', []) if u['username'] != username]
    if len(c['users']) == 0:
        return jsonify({'error': 'Impossible de supprimer le dernier utilisateur'}), 400
    if len(c['users']) == before:
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    save_config(c)
    return jsonify({'ok': True})


@users_bp.route('/api/users/role', methods=['POST'])
@admin_required
def users_role():
    d        = request.json or {}
    username = (d.get('username') or '').strip()
    role     = d.get('role', 'readonly')
    if role not in ('admin', 'readonly'): return jsonify({'error': 'Rôle invalide'}), 400
    if username == session.get('user'):
        return jsonify({'error': 'Impossible de modifier son propre rôle'}), 400
    c = load_config()
    for u in c.get('users', []):
        if u['username'] == username:
            u['role'] = role
            save_config(c)
            return jsonify({'ok': True})
    return jsonify({'error': 'Utilisateur introuvable'}), 404
