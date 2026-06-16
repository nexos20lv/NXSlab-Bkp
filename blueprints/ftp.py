"""Routes FTP — /api/ftp/*"""
import os
import re
from flask import Blueprint, request, jsonify, session
from blueprints.auth import login_required, admin_required
from core.helpers import run, shell, valid_username, setup_data_access
from core.config import get_data_dir

ftp_bp = Blueprint('ftp', __name__)

_NOLOGIN_SHELLS = {'/usr/sbin/nologin', '/bin/false', '/sbin/nologin'}


@ftp_bp.route('/api/ftp/control', methods=['POST'])
@admin_required
def ftp_control():
    action = (request.json or {}).get('action', '')
    if action not in ('start', 'stop', 'restart', 'reload'):
        return jsonify({'error': 'Action invalide'}), 400
    r = run(['systemctl', action, 'vsftpd'])
    return jsonify({'ok': r['ok'], 'output': r['err'] or r['out']})


@ftp_bp.route('/api/ftp/config', methods=['GET', 'POST'])
@login_required
def ftp_config():
    path = '/etc/vsftpd.conf'
    if request.method == 'GET':
        try:
            return jsonify({'content': open(path).read()})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    # NXS-SEC-001: writing the system vsftpd config is admin-only (read stays open
    # to any logged-in user). Mirrors the @admin_required guard on every other
    # ftp mutation route (control / user add / passwd / delete / shell / lock).
    if session.get('role') != 'admin':
        return jsonify({'error': 'Droits administrateur requis'}), 403
    content = (request.json or {}).get('content', '')
    try:
        orig = open(path).read()
        with open(path + '.bak', 'w') as f: f.write(orig)
        with open(path, 'w') as f: f.write(content)
        test = run(['vsftpd', '-olisten=NO', '/etc/vsftpd.conf'], timeout=5)
        if 'error' in (test['err'] or '').lower() and test['rc'] != 0:
            with open(path, 'w') as f: f.write(orig)
            return jsonify({'error': 'Configuration invalide', 'details': test['err']}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ftp_bp.route('/api/ftp/users')
@login_required
def ftp_users():
    r = shell("awk -F: '$3>=1000 && $1!=\"nobody\"{print $1\"|\"$3\"|\"$6\"|\"$7}' /etc/passwd")
    users = []
    for line in r['out'].splitlines():
        p = line.split('|')
        if not p or not p[0].strip():
            continue
        home = p[2].strip() if len(p) > 2 else ''
        if not home or not os.path.isdir(home):
            continue
        sh = p[3].strip() if len(p) > 3 else ''
        users.append({
            'username': p[0].strip(),
            'uid':      p[1].strip() if len(p) > 1 else '',
            'home':     home,
            'shell':    sh,
            'ftp_only': sh in _NOLOGIN_SHELLS,
            'locked':   run(['passwd', '-S', p[0].strip()])['out'].split()[1:2] == ['L'] if p[0].strip() else False
        })
    return jsonify({'users': users})


@ftp_bp.route('/api/ftp/users/add', methods=['POST'])
@admin_required
def ftp_user_add():
    d        = request.json or {}
    username = d.get('username', '').strip().lower()
    password = d.get('password', '')
    data_dir = get_data_dir()
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if len(password) < 6:           return jsonify({'error': 'Mot de passe trop court (min. 6 car.)'}), 400
    r = run(['useradd', '-d', data_dir, '-s', '/usr/sbin/nologin', username])
    if not r['ok'] and 'already exists' not in (r['err'] or ''):
        return jsonify({'error': r['err']}), 500
    if 'already exists' in (r['err'] or ''):
        run(['usermod', '-d', data_dir, '-s', '/usr/sbin/nologin', username])
    setup_data_access(username)
    pw_r = run(['chpasswd'], stdin=f"{username}:{password}\n")
    if not pw_r['ok']:
        return jsonify({'error': pw_r['err'] or 'Erreur mot de passe'}), 500
    return jsonify({'ok': True, 'message': 'Utilisateur créé'})


@ftp_bp.route('/api/ftp/users/passwd', methods=['POST'])
@admin_required
def ftp_user_passwd():
    d        = request.json or {}
    username = d.get('username', '').strip().lower()
    password = d.get('password', '')
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if len(password) < 6:           return jsonify({'error': 'Mot de passe trop court (min. 6 car.)'}), 400
    r = run(['chpasswd'], stdin=f"{username}:{password}\n")
    return jsonify({'ok': r['ok'], 'message': r['err'] or 'Mot de passe modifié'})


@ftp_bp.route('/api/ftp/users/delete', methods=['POST'])
@admin_required
def ftp_user_delete():
    username = (request.json or {}).get('username', '').strip().lower()
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    r = run(['userdel', '-r', username])
    return jsonify({'ok': r['ok'], 'message': r['err'] or 'Supprimé'})


@ftp_bp.route('/api/ftp/users/shell', methods=['POST'])
@admin_required
def ftp_user_shell():
    d        = request.json or {}
    username = d.get('username', '').strip().lower()
    ftp_only = bool(d.get('ftp_only', True))
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    shell_bin = '/usr/sbin/nologin' if ftp_only else '/bin/bash'
    r = run(['usermod', '-s', shell_bin, username])
    return jsonify({'ok': r['ok'], 'message': r['err'] or 'Shell modifié'})


@ftp_bp.route('/api/ftp/users/lock', methods=['POST'])
@admin_required
def ftp_user_lock():
    d        = request.json or {}
    username = d.get('username', '').strip().lower()
    lock     = bool(d.get('lock', True))
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    flag = '-L' if lock else '-U'
    r = run(['passwd', flag, username])
    return jsonify({'ok': r['ok'], 'message': r['err'] or ('Verrouillé' if lock else 'Déverrouillé')})


@ftp_bp.route('/api/ftp/users/homedir', methods=['POST'])
@admin_required
def ftp_user_homedir():
    d        = request.json or {}
    username = d.get('username', '').strip().lower()
    new_home = (d.get('home', '') or '').strip()
    if not valid_username(username):                 return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if not re.match(r'^/[a-zA-Z0-9/_.-]+$', new_home): return jsonify({'error': 'Chemin invalide'}), 400
    os.makedirs(new_home, exist_ok=True)
    r = run(['usermod', '-d', new_home, '-m', username])
    if r['ok']:
        run(['chown', f'{username}:{username}', new_home])
    return jsonify({'ok': r['ok'], 'message': r['err'] or 'Répertoire modifié'})


@ftp_bp.route('/api/ftp/connections')
@login_required
def ftp_connections():
    conns   = shell("ss -tnp 'sport = :21 or dport = :21' 2>/dev/null || netstat -tnp 2>/dev/null | grep ':21 '")
    log     = shell("tail -30 /var/log/vsftpd.log 2>/dev/null || journalctl -u vsftpd -n 30 --no-pager --output=short-iso 2>/dev/null")
    count_r = shell("ss -tn state established 'sport = :21' 2>/dev/null | grep -c ESTAB || echo 0")
    return jsonify({
        'connections': conns['out'] or '(aucune connexion active)',
        'log':         log['out']   or '(aucun journal)',
        'count':       count_r['out'].strip().split('\n')[0]
    })


@ftp_bp.route('/api/ftp/stats')
@login_required
def ftp_stats():
    stats = shell(r"grep -c 'OK UPLOAD\|OK DOWNLOAD' /var/log/vsftpd.log 2>/dev/null || echo 0")
    up    = shell(r"grep -c 'OK UPLOAD'   /var/log/vsftpd.log 2>/dev/null || echo 0")
    down  = shell(r"grep -c 'OK DOWNLOAD' /var/log/vsftpd.log 2>/dev/null || echo 0")
    return jsonify({'total': stats['out'].strip(), 'uploads': up['out'].strip(), 'downloads': down['out'].strip()})