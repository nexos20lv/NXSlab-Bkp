"""Routes Samba — /api/samba/*"""
import configparser
from flask import Blueprint, request, jsonify
from auth import login_required, admin_required
from helpers import run, shell, valid_username

samba_bp = Blueprint('samba', __name__)


@samba_bp.route('/api/samba/control', methods=['POST'])
@admin_required
def samba_control():
    action = (request.json or {}).get('action', '')
    if action not in ('start', 'stop', 'restart', 'reload'):
        return jsonify({'error': 'Action invalide'}), 400
    smbd = run(['systemctl', action, 'smbd'])
    nmbd = run(['systemctl', action, 'nmbd'])
    return jsonify({'ok': smbd['ok'], 'smbd': smbd['err'] or smbd['out'], 'nmbd': nmbd['err'] or nmbd['out']})


@samba_bp.route('/api/samba/connections')
@login_required
def samba_connections():
    r = shell('smbstatus -b 2>/dev/null')
    return jsonify({'output': r['out'] or '(aucune connexion active)'})


@samba_bp.route('/api/samba/shares')
@login_required
def samba_shares():
    try:
        c = configparser.ConfigParser()
        c.read('/etc/samba/smb.conf')
        shares = []
        skip   = {'global', 'homes', 'printers', 'print$', 'ipc$'}
        for s in c.sections():
            if s.lower() not in skip:
                item = dict(c[s]); item['name'] = s; shares.append(item)
        return jsonify({'shares': shares})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@samba_bp.route('/api/samba/config', methods=['GET', 'POST'])
@login_required
def samba_config():
    path = '/etc/samba/smb.conf'
    if request.method == 'GET':
        try:
            return jsonify({'content': open(path).read()})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    content = (request.json or {}).get('content', '')
    try:
        with open(path + '.bak', 'w') as f: f.write(open(path).read())
        with open(path, 'w') as f: f.write(content)
        test = shell('testparm -s 2>&1')
        if test['rc'] != 0:
            with open(path, 'w') as f: f.write(open(path + '.bak').read())
            return jsonify({'error': 'Configuration invalide', 'details': test['out']}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@samba_bp.route('/api/samba/users')
@login_required
def samba_users():
    r = shell('pdbedit -L 2>/dev/null')
    users = []
    for line in r['out'].splitlines():
        if ':' in line:
            p = line.split(':')
            users.append({'username': p[0].strip(), 'uid': p[1].strip() if len(p) > 1 else ''})
    return jsonify({'users': users})


@samba_bp.route('/api/samba/users/add', methods=['POST'])
@admin_required
def samba_user_add():
    d        = request.json or {}
    username = d.get('username', '').strip().lower()
    password = d.get('password', '')
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if len(password) < 6:           return jsonify({'error': 'Mot de passe trop court (min. 6 car.)'}), 400
    if not run(['id', username])['ok']:
        run(['useradd', '-M', '-s', '/usr/sbin/nologin', username])
    r = run(['smbpasswd', '-a', '-s', username], stdin=f"{password}\n{password}\n")
    return jsonify({'ok': r['ok'], 'message': r['out'] or r['err']})


@samba_bp.route('/api/samba/users/passwd', methods=['POST'])
@admin_required
def samba_user_passwd():
    d        = request.json or {}
    username = d.get('username', '').strip().lower()
    password = d.get('password', '')
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if len(password) < 6:           return jsonify({'error': 'Mot de passe trop court (min. 6 car.)'}), 400
    r = run(['smbpasswd', '-s', username], stdin=f"{password}\n{password}\n")
    return jsonify({'ok': r['ok']})


@samba_bp.route('/api/samba/users/delete', methods=['POST'])
@admin_required
def samba_user_delete():
    username = (request.json or {}).get('username', '').strip().lower()
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    run(['smbpasswd', '-x', username])
    run(['userdel', '-r', username])
    return jsonify({'ok': True})
