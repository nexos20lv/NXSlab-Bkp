#!/usr/bin/env python3
"""NXSlab Backup WebUI — Multi-Remote Backup Manager"""

import os
import re
import json
import shutil
import hashlib
import secrets
import subprocess
import configparser
import threading
import uuid
import urllib.request
from functools import wraps
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.start()
    HAS_SCHEDULER = True
except ImportError:
    _scheduler = None
    HAS_SCHEDULER = False

try:
    from flask_sock import Sock
    HAS_SOCK = True
except ImportError:
    HAS_SOCK = False

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 * 1024

if HAS_SOCK:
    sock = Sock(app)

CONFIG_FILE = os.environ.get('CONFIG_FILE', '/etc/nxslab-bkp/config.json')
_APP_START  = datetime.now()

# ─── Config ──────────────────────────────────────────────────────────────────

def _default_config():
    return {
        'users':      [{'username': 'admin', 'password_hash': hashlib.sha256(b'admin').hexdigest(), 'role': 'admin'}],
        'secret_key': secrets.token_hex(32),
        'port':       5080,
        'data_dir':   '/srv/nxslab-bkp',
        'remotes':    []
    }

def _migrate_config(c):
    changed = False
    # Single user → users array
    if 'username' in c and 'users' not in c:
        c['users'] = [{'username': c.pop('username'), 'password_hash': c.pop('password_hash', ''), 'role': 'admin'}]
        changed = True
    elif 'users' not in c:
        c['users'] = [{'username': 'admin', 'password_hash': hashlib.sha256(b'admin').hexdigest(), 'role': 'admin'}]
        changed = True
    # Single remote → remotes array
    if 'remote' in c and 'remotes' not in c:
        remote = c.pop('remote', {})
        backup = c.pop('backup', {})
        remote['backup'] = backup
        remote.setdefault('id',   str(uuid.uuid4())[:8])
        remote.setdefault('name', remote.get('host', 'VPS distant') or 'VPS distant')
        c['remotes'] = [remote]
        changed = True
    elif 'remotes' not in c:
        c['remotes'] = []
        changed = True
    return c, changed

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            c = json.load(f)
    else:
        c = _default_config()
    c, changed = _migrate_config(c)
    if changed:
        save_config(c)
    return c

def save_config(data):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)

cfg = load_config()
app.secret_key = cfg.get('secret_key', secrets.token_hex(32))

# ─── Helpers ─────────────────────────────────────────────────────────────────

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def valid_username(u: str) -> bool:
    return bool(re.match(r'^[a-z_][a-z0-9_.-]{0,30}$', u))

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

def human_size(n):
    n = float(n)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(n) < 1024.0 or unit == 'TB':
            return f"{int(n)} B" if unit == 'B' else f"{n:.1f} {unit}"
        n /= 1024.0

def get_data_dir():
    return load_config().get('data_dir', '/srv/nxslab-bkp')

def _get_remote(remote_id: str):
    for r in load_config().get('remotes', []):
        if r.get('id') == remote_id:
            return r
    return None

# ─── Auth decorators ─────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            if request.is_json or request.path.startswith('/api/') or request.path.startswith('/ws/'):
                return jsonify({'error': 'Non autorisé'}), 401
            return redirect(url_for('login'))
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

# ─── Auth ────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() or request.form
        c    = load_config()
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        for u in c.get('users', []):
            if u.get('username') == username and hash_pw(password) == u.get('password_hash', ''):
                session.permanent  = True
                session['logged_in'] = True
                session['user']    = username
                session['role']    = u.get('role', 'readonly')
                payload = {'ok': True, 'role': session['role']}
                return jsonify(payload) if request.is_json else redirect(url_for('index'))
        return (jsonify({'error': 'Identifiants incorrects'}), 401) if request.is_json \
               else render_template('login.html', error='Identifiants incorrects')
    if session.get('logged_in'):
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

# ─── Health check ─────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    c = load_config()
    uptime_sec = int((datetime.now() - _APP_START).total_seconds())
    remotes_status = []
    for r in c.get('remotes', []):
        rid   = r.get('id', '')
        state = _get_backup_state(rid)
        remotes_status.append({
            'id':          rid,
            'name':        r.get('name', ''),
            'host':        r.get('host', ''),
            'last_backup': state.get('last_run'),
            'last_status': state.get('last_status'),
        })
    return jsonify({
        'status':        'ok',
        'version':       '2.1.0',
        'uptime_seconds': uptime_sec,
        'services':      {'samba': svc_state('smbd'), 'ftp': svc_state('vsftpd')},
        'remotes':       remotes_status,
        'has_paramiko':  HAS_PARAMIKO,
        'has_scheduler': HAS_SCHEDULER,
        'has_websocket': HAS_SOCK,
    })

# ─── Status ──────────────────────────────────────────────────────────────────

@app.route('/api/status')
@login_required
def api_status():
    ftp_conns = shell("ss -tn state established '( dport = :21 or sport = :21 )' 2>/dev/null | grep -c ESTAB || echo 0")
    return jsonify({
        'samba':     svc_state('smbd'),
        'nmbd':      svc_state('nmbd'),
        'ftp':       svc_state('vsftpd'),
        'hostname':  shell('hostname').get('out', '').strip(),
        'uptime':    shell('uptime -p').get('out', '').strip(),
        'ftp_conns': ftp_conns['out'].strip(),
        'ts':        datetime.now().strftime('%H:%M:%S'),
        'role':      session.get('role', 'readonly'),
    })

# ─── Remotes CRUD ────────────────────────────────────────────────────────────

@app.route('/api/remotes')
@login_required
def remotes_list():
    c = load_config()
    result = []
    for r in c.get('remotes', []):
        entry = {k: v for k, v in r.items() if k not in ('password', 'key_passphrase', 'backup')}
        if r.get('password'):
            entry['password'] = '**hidden**'
        state = _get_backup_state(r.get('id', ''))
        entry['last_run']    = state.get('last_run')
        entry['last_status'] = state.get('last_status')
        entry['running']     = state.get('running', False)
        result.append(entry)
    return jsonify({'remotes': result})

@app.route('/api/remotes/add', methods=['POST'])
@admin_required
def remotes_add():
    d    = request.json or {}
    name = (d.get('name') or '').strip()
    host = (d.get('host') or '').strip()
    if not name or not host:
        return jsonify({'error': 'Nom et hôte requis'}), 400
    c      = load_config()
    new_id = str(uuid.uuid4())[:8]
    while any(r.get('id') == new_id for r in c.get('remotes', [])):
        new_id = str(uuid.uuid4())[:8]
    slug = re.sub(r'[^a-z0-9_-]', '-', name.lower())[:20] or new_id
    remote = {
        'id':             new_id,
        'name':           name,
        'host':           host,
        'port':           int(d.get('port', 22)),
        'user':           (d.get('user') or 'root').strip(),
        'auth_type':      d.get('auth_type', 'key'),
        'key_path':       (d.get('key_path') or '/root/.ssh/id_rsa').strip(),
        'key_passphrase': d.get('key_passphrase', ''),
        'password':       d.get('password', ''),
        'backup': {
            'targets':          ['docker', 'websites', 'configs'],
            'subdir':           slug,
            'compression':      'gz',
            'max_count':        7,
            'max_days':         0,
            'schedule_enabled': False,
            'schedule':         '0 2 * * *',
            'docker_all':       True,
            'docker_stop':      False,
            'docker_names':     [],
            'web_paths':        ['/var/www/html'],
            'config_paths':     ['/etc/nginx'],
            'excludes':         [],
            'pre_hook':         '',
            'post_hook':        '',
            'webhook_url':      '',
            'verify':           False,
            'databases':        {'mysql': [], 'postgres': []}
        }
    }
    c.setdefault('remotes', []).append(remote)
    save_config(c)
    _apply_schedule()
    return jsonify({'ok': True, 'id': new_id})

@app.route('/api/remotes/update', methods=['POST'])
@admin_required
def remotes_update():
    d         = request.json or {}
    remote_id = (d.get('id') or '').strip()
    if not remote_id:
        return jsonify({'error': 'ID requis'}), 400
    c = load_config()
    for i, r in enumerate(c.get('remotes', [])):
        if r.get('id') == remote_id:
            for key in ('name', 'host', 'user', 'auth_type', 'key_path', 'key_passphrase'):
                if key in d:
                    r[key] = d[key]
            if 'port' in d:
                r['port'] = int(d['port'])
            if d.get('password') and d['password'] != '**hidden**':
                r['password'] = d['password']
            c['remotes'][i] = r
            save_config(c)
            _apply_schedule()
            return jsonify({'ok': True})
    return jsonify({'error': 'Remote introuvable'}), 404

@app.route('/api/remotes/delete', methods=['POST'])
@admin_required
def remotes_delete():
    remote_id = (request.json or {}).get('id', '').strip()
    if not remote_id:
        return jsonify({'error': 'ID requis'}), 400
    c      = load_config()
    before = len(c.get('remotes', []))
    c['remotes'] = [r for r in c.get('remotes', []) if r.get('id') != remote_id]
    if len(c['remotes']) == before:
        return jsonify({'error': 'Remote introuvable'}), 404
    save_config(c)
    _apply_schedule()
    return jsonify({'ok': True})

# ─── Remote real-time stats ──────────────────────────────────────────────────

@app.route('/api/remote/<remote_id>/stats')
@login_required
def remote_stats(remote_id):
    remote = _get_remote(remote_id)
    if not remote:
        return jsonify({'error': 'Remote introuvable'}), 404
    try:
        ssh = _ssh_connect(remote)
        _, cpu_out,  _ = _ssh_exec(ssh, "top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'", timeout=10)
        _, mem_out,  _ = _ssh_exec(ssh, "free -m | awk 'NR==2{print $2,$3,$4}'",            timeout=10)
        _, disk_out, _ = _ssh_exec(ssh,
            "df -h --output=source,size,used,avail,pcent,target 2>/dev/null | grep -v tmpfs | grep -v udev | grep -v Filesystem",
            timeout=10)
        _, load_out, _ = _ssh_exec(ssh, 'cat /proc/loadavg',  timeout=10)
        _, up_out,   _ = _ssh_exec(ssh, 'uptime -p',           timeout=10)
        _, dock_out, _ = _ssh_exec(ssh,
            'docker ps --format "{{.Names}}|{{.Status}}" 2>/dev/null | head -30',
            timeout=10)
        _, kern_out, _ = _ssh_exec(ssh, 'uname -r', timeout=5)
        ssh.close()

        m     = mem_out.strip().split()
        total = int(m[0]) if m else 0
        used  = int(m[1]) if len(m) > 1 else 0
        mem_pct = round((used / total) * 100) if total else 0

        disks = []
        for line in disk_out.strip().splitlines():
            p = line.split()
            if len(p) >= 6:
                try: pct_int = int(p[4].replace('%', ''))
                except: pct_int = 0
                disks.append({'device': p[0], 'size': p[1], 'used': p[2],
                               'avail': p[3], 'percent': p[4], 'percent_int': pct_int, 'mount': p[5]})

        lp = load_out.split()
        containers = []
        for line in dock_out.strip().splitlines():
            parts = line.split('|')
            if parts and parts[0].strip():
                containers.append({'name': parts[0].strip(), 'status': parts[1].strip() if len(parts) > 1 else ''})

        return jsonify({
            'ok':         True,
            'cpu':        cpu_out.strip() or '0',
            'memory':     {'total': total, 'used': used, 'free': total - used, 'percent': mem_pct},
            'disks':      disks,
            'load':       {'1m': lp[0] if lp else '0', '5m': lp[1] if len(lp) > 1 else '0',
                           '15m': lp[2] if len(lp) > 2 else '0'},
            'uptime':     up_out.strip(),
            'containers': containers,
            'kernel':     kern_out.strip(),
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ─── Backup history (all remotes for chart) ──────────────────────────────────

@app.route('/api/backup/history')
@login_required
def backup_history():
    c        = load_config()
    data_dir = get_data_dir()
    result   = {}
    for remote in c.get('remotes', []):
        rid    = remote.get('id', '')
        subdir = (remote.get('backup', {}).get('subdir', '') or rid).strip('/')
        bkp_root = os.path.join(data_dir, 'backups', subdir)
        points = []
        if os.path.isdir(bkp_root):
            for name in sorted(os.listdir(bkp_root)):
                full = os.path.join(bkp_root, name)
                if not os.path.isdir(full):
                    continue
                size  = sum(f.stat().st_size for f in Path(full).rglob('*') if f.is_file())
                mtime = datetime.fromtimestamp(os.path.getmtime(full)).strftime('%Y-%m-%d %H:%M')
                status = 'unknown'
                mp = os.path.join(full, 'manifest.json')
                if os.path.exists(mp):
                    try:
                        with open(mp) as f:
                            status = json.load(f).get('status', 'unknown')
                    except Exception:
                        pass
                points.append({'date': mtime, 'size': size, 'size_h': human_size(size),
                                'id': name, 'status': status})
        result[rid] = {'name': remote.get('name', rid), 'points': points}
    return jsonify({'history': result})

# ─── Samba ───────────────────────────────────────────────────────────────────

@app.route('/api/samba/control', methods=['POST'])
@admin_required
def samba_control():
    action = (request.json or {}).get('action', '')
    if action not in ('start', 'stop', 'restart', 'reload'):
        return jsonify({'error': 'Action invalide'}), 400
    smbd = run(['systemctl', action, 'smbd'])
    nmbd = run(['systemctl', action, 'nmbd'])
    return jsonify({'ok': smbd['ok'], 'smbd': smbd['err'] or smbd['out'], 'nmbd': nmbd['err'] or nmbd['out']})

@app.route('/api/samba/connections')
@login_required
def samba_connections():
    r = shell('smbstatus -b 2>/dev/null')
    return jsonify({'output': r['out'] or '(aucune connexion active)'})

@app.route('/api/samba/shares')
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

@app.route('/api/samba/config', methods=['GET', 'POST'])
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

@app.route('/api/samba/users')
@login_required
def samba_users():
    r = shell('pdbedit -L 2>/dev/null')
    users = []
    for line in r['out'].splitlines():
        if ':' in line:
            p = line.split(':')
            users.append({'username': p[0].strip(), 'uid': p[1].strip() if len(p) > 1 else ''})
    return jsonify({'users': users})

@app.route('/api/samba/users/add', methods=['POST'])
@admin_required
def samba_user_add():
    d = request.json or {}
    username = d.get('username', '').strip().lower()
    password = d.get('password', '')
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if len(password) < 6:           return jsonify({'error': 'Mot de passe trop court (min. 6 car.)'}), 400
    if not run(['id', username])['ok']:
        run(['useradd', '-M', '-s', '/usr/sbin/nologin', username])
    r = run(['smbpasswd', '-a', '-s', username], stdin=f"{password}\n{password}\n")
    return jsonify({'ok': r['ok'], 'message': r['out'] or r['err']})

@app.route('/api/samba/users/passwd', methods=['POST'])
@admin_required
def samba_user_passwd():
    d = request.json or {}
    username = d.get('username', '').strip().lower()
    password = d.get('password', '')
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if len(password) < 6:           return jsonify({'error': 'Mot de passe trop court (min. 6 car.)'}), 400
    r = run(['smbpasswd', '-s', username], stdin=f"{password}\n{password}\n")
    return jsonify({'ok': r['ok']})

@app.route('/api/samba/users/delete', methods=['POST'])
@admin_required
def samba_user_delete():
    username = (request.json or {}).get('username', '').strip().lower()
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    r = run(['smbpasswd', '-x', username])
    return jsonify({'ok': r['ok']})

# ─── FTP ─────────────────────────────────────────────────────────────────────

_FTP_NOLOGIN_SHELLS = {'/usr/sbin/nologin', '/bin/false', '/sbin/nologin'}

@app.route('/api/ftp/control', methods=['POST'])
@admin_required
def ftp_control():
    action = (request.json or {}).get('action', '')
    if action not in ('start', 'stop', 'restart', 'reload'):
        return jsonify({'error': 'Action invalide'}), 400
    r = run(['systemctl', action, 'vsftpd'])
    return jsonify({'ok': r['ok'], 'output': r['err'] or r['out']})

@app.route('/api/ftp/config', methods=['GET', 'POST'])
@login_required
def ftp_config():
    path = '/etc/vsftpd.conf'
    if request.method == 'GET':
        try:
            return jsonify({'content': open(path).read()})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
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

@app.route('/api/ftp/users')
@login_required
def ftp_users():
    r = shell(r"awk -F: '$3>=1000 && $1!=\"nobody\"{print $1\"|\"$3\"|\"$6\"|\"$7}' /etc/passwd")
    users = []
    for line in r['out'].splitlines():
        p = line.split('|')
        if not p or not p[0].strip():
            continue
        sh = p[3].strip() if len(p) > 3 else ''
        users.append({
            'username': p[0].strip(),
            'uid':      p[1].strip() if len(p) > 1 else '',
            'home':     p[2].strip() if len(p) > 2 else '',
            'shell':    sh,
            'ftp_only': sh in _FTP_NOLOGIN_SHELLS,
            'locked':   run(['passwd', '-S', p[0].strip()])['out'].split()[1:2] == ['L'] if p[0].strip() else False
        })
    return jsonify({'users': users})

@app.route('/api/ftp/users/add', methods=['POST'])
@admin_required
def ftp_user_add():
    d        = request.json or {}
    username = d.get('username', '').strip().lower()
    password = d.get('password', '')
    home     = (d.get('home', '') or f'/home/{username}').strip()
    ftp_only = bool(d.get('ftp_only', True))
    if not valid_username(username):                  return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if len(password) < 6:                            return jsonify({'error': 'Mot de passe trop court (min. 6 car.)'}), 400
    if not re.match(r'^/[a-zA-Z0-9/_.-]+$', home):  return jsonify({'error': 'Chemin invalide'}), 400
    shell_bin = '/usr/sbin/nologin' if ftp_only else '/bin/bash'
    r = run(['useradd', '-m', '-d', home, '-s', shell_bin, username])
    if not r['ok'] and 'already exists' not in r['err']:
        return jsonify({'error': r['err']}), 500
    os.makedirs(home, exist_ok=True)
    run(['chown', f'{username}:{username}', home])
    run(['chmod', '755', home])
    pw_r = run(['chpasswd'], stdin=f"{username}:{password}\n")
    if not pw_r['ok']:
        return jsonify({'error': pw_r['err'] or 'Erreur mot de passe'}), 500
    return jsonify({'ok': True, 'message': 'Utilisateur créé'})

@app.route('/api/ftp/users/passwd', methods=['POST'])
@admin_required
def ftp_user_passwd():
    d = request.json or {}
    username = d.get('username', '').strip().lower()
    password = d.get('password', '')
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if len(password) < 6:           return jsonify({'error': 'Mot de passe trop court (min. 6 car.)'}), 400
    r = run(['chpasswd'], stdin=f"{username}:{password}\n")
    return jsonify({'ok': r['ok'], 'message': r['err'] or 'Mot de passe modifié'})

@app.route('/api/ftp/users/delete', methods=['POST'])
@admin_required
def ftp_user_delete():
    username = (request.json or {}).get('username', '').strip().lower()
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    r = run(['userdel', '-r', username])
    return jsonify({'ok': r['ok'], 'message': r['err'] or 'Supprimé'})

@app.route('/api/ftp/users/shell', methods=['POST'])
@admin_required
def ftp_user_shell():
    d = request.json or {}
    username = d.get('username', '').strip().lower()
    ftp_only = bool(d.get('ftp_only', True))
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    shell_bin = '/usr/sbin/nologin' if ftp_only else '/bin/bash'
    r = run(['usermod', '-s', shell_bin, username])
    return jsonify({'ok': r['ok'], 'message': r['err'] or 'Shell modifié'})

@app.route('/api/ftp/users/lock', methods=['POST'])
@admin_required
def ftp_user_lock():
    d = request.json or {}
    username = d.get('username', '').strip().lower()
    lock     = bool(d.get('lock', True))
    if not valid_username(username): return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    flag = '-L' if lock else '-U'
    r = run(['passwd', flag, username])
    return jsonify({'ok': r['ok'], 'message': r['err'] or ('Verrouillé' if lock else 'Déverrouillé')})

@app.route('/api/ftp/users/homedir', methods=['POST'])
@admin_required
def ftp_user_homedir():
    d        = request.json or {}
    username = d.get('username', '').strip().lower()
    new_home = (d.get('home', '') or '').strip()
    if not valid_username(username):                      return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if not re.match(r'^/[a-zA-Z0-9/_.-]+$', new_home):  return jsonify({'error': 'Chemin invalide'}), 400
    os.makedirs(new_home, exist_ok=True)
    r = run(['usermod', '-d', new_home, '-m', username])
    if r['ok']:
        run(['chown', f'{username}:{username}', new_home])
    return jsonify({'ok': r['ok'], 'message': r['err'] or 'Répertoire modifié'})

@app.route('/api/ftp/connections')
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

@app.route('/api/ftp/stats')
@login_required
def ftp_stats():
    stats = shell(r"grep -c 'OK UPLOAD\|OK DOWNLOAD' /var/log/vsftpd.log 2>/dev/null || echo 0")
    up    = shell(r"grep -c 'OK UPLOAD'   /var/log/vsftpd.log 2>/dev/null || echo 0")
    down  = shell(r"grep -c 'OK DOWNLOAD' /var/log/vsftpd.log 2>/dev/null || echo 0")
    return jsonify({'total': stats['out'].strip(), 'uploads': up['out'].strip(), 'downloads': down['out'].strip()})

# ─── Système ─────────────────────────────────────────────────────────────────

@app.route('/api/system')
@login_required
def api_system():
    disk_r = shell("df -h --output=source,size,used,avail,pcent,target 2>/dev/null | grep -v tmpfs | grep -v udev | grep -v Filesystem")
    disks  = []
    for line in disk_r['out'].splitlines():
        p = line.split()
        if len(p) >= 6:
            try: pct_int = int(p[4].replace('%', ''))
            except: pct_int = 0
            disks.append({'device': p[0], 'size': p[1], 'used': p[2], 'avail': p[3],
                          'percent': p[4], 'percent_int': pct_int, 'mount': p[5]})
    mem_r = shell("free -m | awk 'NR==2{print $2,$3,$4}'")
    m     = mem_r['out'].strip().split()
    total = int(m[0]) if m else 0
    used  = int(m[1]) if len(m) > 1 else 0
    free  = int(m[2]) if len(m) > 2 else 0
    mem_pct = round((used / total) * 100) if total else 0
    cpu_r  = shell("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'")
    load_r = shell('cat /proc/loadavg')
    lp     = load_r['out'].split()
    return jsonify({
        'disks':  disks,
        'memory': {'total': total, 'used': used, 'free': free, 'percent': mem_pct},
        'cpu':    cpu_r['out'].strip() or '0',
        'load':   {'1m': lp[0] if lp else '0', '5m': lp[1] if len(lp) > 1 else '0', '15m': lp[2] if len(lp) > 2 else '0'},
        'uptime': shell('uptime -p')['out'].strip()
    })

# ─── Logs ────────────────────────────────────────────────────────────────────

@app.route('/api/logs/<service>')
@login_required
def api_logs(service):
    if service not in ('samba', 'ftp', 'system'):
        return jsonify({'error': 'Service inconnu'}), 400
    lines = min(int(request.args.get('lines', 100)), 500)
    cmds = {
        'samba':  f'journalctl -u smbd -n {lines} --no-pager --output=short-iso 2>/dev/null || tail -n {lines} /var/log/samba/log.smbd 2>/dev/null',
        'ftp':    f'journalctl -u vsftpd -n {lines} --no-pager --output=short-iso 2>/dev/null || tail -n {lines} /var/log/vsftpd.log 2>/dev/null',
        'system': f'journalctl -n {lines} --no-pager --output=short-iso 2>/dev/null',
    }
    r = shell(cmds[service])
    return jsonify({'logs': r['out'] or '(aucun journal disponible)', 'err': r['err'] if not r['ok'] else ''})

# ─── Users (multi-user management) ───────────────────────────────────────────

@app.route('/api/settings/me')
@login_required
def settings_me():
    return jsonify({'username': session.get('user'), 'role': session.get('role')})

@app.route('/api/settings/password', methods=['POST'])
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

@app.route('/api/users')
@admin_required
def users_list():
    c = load_config()
    users = [{'username': u['username'], 'role': u.get('role', 'readonly')} for u in c.get('users', [])]
    return jsonify({'users': users})

@app.route('/api/users/add', methods=['POST'])
@admin_required
def users_add():
    d        = request.json or {}
    username = (d.get('username') or '').strip().lower()
    password = d.get('password') or ''
    role     = d.get('role', 'readonly')
    if not re.match(r'^[a-z_][a-z0-9_.-]{0,30}$', username):
        return jsonify({'error': "Nom d'utilisateur invalide"}), 400
    if len(password) < 8:               return jsonify({'error': 'Mot de passe trop court (min. 8 car.)'}), 400
    if role not in ('admin', 'readonly'): return jsonify({'error': 'Rôle invalide'}), 400
    c = load_config()
    if any(u['username'] == username for u in c.get('users', [])):
        return jsonify({'error': 'Utilisateur déjà existant'}), 400
    c.setdefault('users', []).append({'username': username, 'password_hash': hash_pw(password), 'role': role})
    save_config(c)
    return jsonify({'ok': True})

@app.route('/api/users/delete', methods=['POST'])
@admin_required
def users_delete():
    username = (request.json or {}).get('username', '').strip()
    if username == session.get('user'):
        return jsonify({'error': 'Impossible de supprimer son propre compte'}), 400
    c = load_config()
    before   = len(c.get('users', []))
    c['users'] = [u for u in c.get('users', []) if u['username'] != username]
    if len(c['users']) == 0:
        return jsonify({'error': 'Impossible de supprimer le dernier utilisateur'}), 400
    if len(c['users']) == before:
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    save_config(c)
    return jsonify({'ok': True})

@app.route('/api/users/role', methods=['POST'])
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

# ─── File explorer ───────────────────────────────────────────────────────────

def safe_path(rel):
    base = os.path.realpath(get_data_dir())
    full = os.path.realpath(os.path.join(base, rel.lstrip('/')))
    if full == base or full.startswith(base + os.sep):
        return full
    return None

@app.route('/api/files/list')
@login_required
def files_list():
    rel  = request.args.get('path', '/')
    full = safe_path(rel)
    if not full: return jsonify({'error': 'Chemin invalide'}), 403
    if not os.path.isdir(full): return jsonify({'error': 'Répertoire inexistant'}), 404
    base    = os.path.realpath(get_data_dir())
    entries = []
    try:
        for name in sorted(os.listdir(full), key=str.lower):
            ep   = os.path.join(full, name)
            stat = os.stat(ep)
            is_d = os.path.isdir(ep)
            rel_e = os.path.relpath(ep, base).replace('\\', '/')
            entries.append({
                'name':   name,
                'type':   'dir' if is_d else 'file',
                'size':   None if is_d else stat.st_size,
                'size_h': '—' if is_d else human_size(stat.st_size),
                'mtime':  datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                'path':   '/' + rel_e,
            })
    except PermissionError:
        return jsonify({'error': 'Permission refusée'}), 403
    entries.sort(key=lambda e: (0 if e['type'] == 'dir' else 1, e['name'].lower()))
    rel_clean   = rel.strip('/')
    parent      = ('/' + '/'.join(rel_clean.split('/')[:-1])) if rel_clean else None
    rel_display = os.path.relpath(full, base).replace('\\', '/')
    path_display = '/' if rel_display == '.' else '/' + rel_display
    return jsonify({'path': path_display, 'entries': entries, 'parent': parent})

@app.route('/api/files/download')
@login_required
def files_download():
    rel  = request.args.get('path', '')
    full = safe_path(rel)
    if not full or not os.path.isfile(full): return jsonify({'error': 'Fichier introuvable'}), 404
    return send_file(full, as_attachment=True)

@app.route('/api/files/upload', methods=['POST'])
@login_required
def files_upload():
    rel  = request.args.get('path', '/')
    full = safe_path(rel)
    if not full or not os.path.isdir(full): return jsonify({'error': 'Répertoire invalide'}), 400
    files = request.files.getlist('files')
    if not files: return jsonify({'error': 'Aucun fichier reçu'}), 400
    saved = []
    for f in files:
        if not f.filename: continue
        safe_name = os.path.basename(f.filename.replace('..', ''))
        if not safe_name: continue
        f.save(os.path.join(full, safe_name))
        saved.append(safe_name)
    return jsonify({'ok': True, 'saved': saved})

@app.route('/api/files/mkdir', methods=['POST'])
@login_required
def files_mkdir():
    d      = request.json or {}
    parent = d.get('path', '/')
    name   = d.get('name', '').strip()
    if not name or '/' in name or name in ('..', '.'):
        return jsonify({'error': 'Nom invalide'}), 400
    full_p = safe_path(parent)
    if not full_p or not os.path.isdir(full_p): return jsonify({'error': 'Répertoire parent invalide'}), 400
    try:
        os.makedirs(os.path.join(full_p, name), exist_ok=False)
        return jsonify({'ok': True})
    except FileExistsError: return jsonify({'error': 'Ce dossier existe déjà'}), 400
    except Exception as e:  return jsonify({'error': str(e)}), 500

@app.route('/api/files/delete', methods=['POST'])
@login_required
def files_delete():
    rel  = (request.json or {}).get('path', '')
    full = safe_path(rel)
    base = os.path.realpath(get_data_dir())
    if not full or full == base: return jsonify({'error': 'Impossible de supprimer la racine'}), 403
    if not os.path.exists(full): return jsonify({'error': 'Introuvable'}), 404
    try:
        shutil.rmtree(full) if os.path.isdir(full) else os.remove(full)
        return jsonify({'ok': True})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/files/rename', methods=['POST'])
@login_required
def files_rename():
    d        = request.json or {}
    rel      = d.get('path', '')
    new_name = d.get('name', '').strip()
    if not new_name or '/' in new_name or new_name in ('..', '.'):
        return jsonify({'error': 'Nom invalide'}), 400
    full = safe_path(rel)
    if not full or not os.path.exists(full): return jsonify({'error': 'Introuvable'}), 404
    new_full = os.path.join(os.path.dirname(full), new_name)
    if os.path.exists(new_full): return jsonify({'error': 'Un élément avec ce nom existe déjà'}), 400
    try:
        os.rename(full, new_full)
        return jsonify({'ok': True})
    except Exception as e: return jsonify({'error': str(e)}), 500

# ─── Backup — SSH helpers ────────────────────────────────────────────────────

def _ssh_connect(remote: dict):
    if not HAS_PARAMIKO:
        raise RuntimeError("paramiko non installé — lancez: pip install paramiko")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    host = remote.get('host', '').strip()
    if not host: raise ValueError("Hôte VPS distant non configuré")
    port = int(remote.get('port', 22))
    user = remote.get('user', 'root').strip()
    auth = remote.get('auth_type', 'key')
    if auth == 'key':
        ssh.connect(host, port=port, username=user,
                    key_filename=remote.get('key_path', '/root/.ssh/id_rsa').strip(),
                    passphrase=remote.get('key_passphrase') or None,
                    timeout=15, banner_timeout=15)
    else:
        ssh.connect(host, port=port, username=user,
                    password=remote.get('password', ''), timeout=15, banner_timeout=15)
    return ssh

def _ssh_exec(ssh, cmd: str, timeout: int = 300):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    rc  = stdout.channel.recv_exit_status()
    return rc, out, err

def _stream_remote(ssh, remote_cmd: str, local_path: str) -> int:
    transport = ssh.get_transport()
    chan = transport.open_session()
    chan.exec_command(remote_cmd)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, 'wb') as f:
        while True:
            chunk = chan.recv(65536)
            if not chunk: break
            f.write(chunk)
    rc = chan.recv_exit_status()
    chan.close()
    return rc

def _verify_archive(local_path: str, compression: str) -> bool:
    if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
        return False
    flag_map = {'gz': 'z', 'bz2': 'j', 'none': ''}
    f = flag_map.get(compression, 'z')
    result = subprocess.run(['tar', f't{f}f', local_path], capture_output=True, timeout=60)
    return result.returncode == 0

def _notify(url: str, payload: dict):
    if not url: return
    try:
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            url, data=data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'NXSlab-Bkp/2.1'},
            method='POST')
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

# ─── Backup — state & scheduler ──────────────────────────────────────────────

_backup_states: dict = {}
_backup_locks:  dict = {}

def _get_backup_state(remote_id: str) -> dict:
    if remote_id not in _backup_states:
        _backup_states[remote_id] = {
            'running': False, 'progress': '', 'percent': 0,
            'last_run': None, 'last_status': None, 'last_log': [],
            'last_manifest': None
        }
    return _backup_states[remote_id]

def _get_backup_lock(remote_id: str) -> threading.Lock:
    if remote_id not in _backup_locks:
        _backup_locks[remote_id] = threading.Lock()
    return _backup_locks[remote_id]

def _log(state: dict, msg: str):
    ts = datetime.now().strftime('%H:%M:%S')
    state['last_log'].append(f"[{ts}] {msg}")
    state['progress'] = msg

def _apply_schedule():
    if not HAS_SCHEDULER: return
    try:
        _scheduler.remove_all_jobs()
        for remote in load_config().get('remotes', []):
            rid    = remote.get('id', '')
            backup = remote.get('backup', {})
            if backup.get('schedule_enabled') and backup.get('schedule'):
                parts = backup['schedule'].split()
                if len(parts) == 5:
                    _scheduler.add_job(
                        lambda r=rid: run_backup(r) if not _get_backup_state(r).get('running') else None,
                        CronTrigger(minute=parts[0], hour=parts[1],
                                    day=parts[2], month=parts[3], day_of_week=parts[4]),
                        id=f'backup_{rid}', replace_existing=True
                    )
    except Exception:
        pass

# ─── Backup — run ────────────────────────────────────────────────────────────

def run_backup(remote_id: str):
    remote = _get_remote(remote_id)
    if not remote:
        return False, "Remote introuvable"

    state = _get_backup_state(remote_id)
    with _get_backup_lock(remote_id):
        if state.get('running'):
            return False, "Backup déjà en cours"

    state.update({
        'running': True, 'progress': 'Démarrage...', 'percent': 0,
        'last_run': datetime.now().isoformat(), 'last_status': None,
        'last_log': [], 'last_manifest': None
    })

    def _run():
        ssh = None
        manifest = {'started_at': datetime.now().isoformat(), 'remote': remote_id,
                    'remote_name': remote.get('name', ''), 'targets': {}, 'errors': [], 'files': []}
        try:
            backup      = remote.get('backup', {})
            data_dir    = get_data_dir()
            subdir      = (backup.get('subdir', '') or remote_id).strip('/')
            ts          = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_path = os.path.join(data_dir, 'backups', subdir, ts)
            os.makedirs(backup_path, exist_ok=True)

            compression  = backup.get('compression', 'gz')
            tar_flag     = {'gz': 'z', 'bz2': 'j', 'none': ''}.get(compression, 'z')
            ext          = {'gz': '.tar.gz', 'bz2': '.tar.bz2', 'none': '.tar'}.get(compression, '.tar.gz')
            verify       = backup.get('verify', False)
            exclude_args = ' '.join(f'--exclude="{e}"' for e in backup.get('excludes', []) if e.strip())

            pre_hook = backup.get('pre_hook', '').strip()
            if pre_hook:
                _log(state, f"Hook pré-backup: {pre_hook}")
            state['percent'] = 2

            _log(state, f"Connexion SSH → {remote.get('host', '?')}:{remote.get('port', 22)}")
            ssh = _ssh_connect(remote)
            _log(state, "Connexion établie")
            state['percent'] = 5

            if pre_hook:
                rc, out, err = _ssh_exec(ssh, pre_hook, timeout=120)
                _log(state, f"  Hook: {'OK' if rc == 0 else 'ERREUR'} {(out + err).strip()[:200]}")

            targets = backup.get('targets', ['docker', 'websites', 'configs'])

            # ── Docker ────────────────────────────────────────────────────
            if 'docker' in targets:
                _log(state, "══ Backup Docker ══")
                state['percent'] = 10
                docker_dir = os.path.join(backup_path, 'docker')
                os.makedirs(docker_dir, exist_ok=True)
                manifest['targets']['docker'] = {'containers': {}}

                if backup.get('docker_all', True):
                    rc, out, _ = _ssh_exec(ssh, 'docker ps --format "{{.Names}}"')
                    containers = [c.strip() for c in out.splitlines() if c.strip()]
                else:
                    containers = [c.strip() for c in backup.get('docker_names', []) if c.strip()]

                _log(state, f"  Containers: {', '.join(containers) if containers else 'aucun'}")
                stop_before = backup.get('docker_stop', False)

                for i, cname in enumerate(containers):
                    _log(state, f"  [{i+1}/{len(containers)}] {cname}")
                    cdir = os.path.join(docker_dir, cname)
                    os.makedirs(cdir, exist_ok=True)
                    manifest['targets']['docker']['containers'][cname] = {'volumes': [], 'errors': []}

                    if stop_before:
                        _log(state, f"    Arrêt {cname}..."); _ssh_exec(ssh, f'docker stop {cname}', timeout=30)

                    rc, out, _ = _ssh_exec(ssh, f'docker inspect {cname} 2>/dev/null')
                    if rc == 0 and out.strip():
                        with open(os.path.join(cdir, 'inspect.json'), 'w') as f: f.write(out)

                    fmt = '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}|{{.Destination}}\n{{end}}{{end}}'
                    rc, out, _ = _ssh_exec(ssh, f"docker inspect --format '{fmt}' {cname} 2>/dev/null")
                    for line in out.splitlines():
                        parts = line.strip().split('|')
                        if not parts: continue
                        vol_name  = parts[0]
                        local_vol = os.path.join(cdir, vol_name + ext)
                        _log(state, f"    Volume: {vol_name}")
                        cmd = f'docker run --rm -v {vol_name}:/bkp_vol:ro alpine tar c{tar_flag}f - -C /bkp_vol . 2>/dev/null'
                        rc2 = _stream_remote(ssh, cmd, local_vol)
                        if rc2 != 0:
                            err_msg = f"Erreur volume {vol_name} (rc={rc2})"
                            _log(state, f"    ⚠ {err_msg}")
                            manifest['targets']['docker']['containers'][cname]['errors'].append(err_msg)
                        else:
                            sz = os.path.getsize(local_vol) if os.path.exists(local_vol) else 0
                            manifest['targets']['docker']['containers'][cname]['volumes'].append(
                                {'name': vol_name, 'file': vol_name + ext, 'size': sz})
                            if verify:
                                ok = _verify_archive(local_vol, compression)
                                _log(state, f"    Vérif: {'✓' if ok else '✗ CORROMPU'}")
                                if not ok: manifest['errors'].append(f"Archive corrompue: {local_vol}")

                    if stop_before:
                        _log(state, f"    Redémarrage {cname}..."); _ssh_exec(ssh, f'docker start {cname}', timeout=30)

            state['percent'] = 35

            # ── Bases de données ──────────────────────────────────────────
            if 'databases' in targets:
                _log(state, "══ Backup Bases de données ══")
                db_dir = os.path.join(backup_path, 'databases')
                os.makedirs(db_dir, exist_ok=True)
                manifest['targets']['databases'] = {'dumps': []}

                for db_entry in backup.get('databases', {}).get('mysql', []):
                    db_name = db_entry.get('name', '')
                    _log(state, f"  MySQL: {db_name}")
                    dcname = db_entry.get('docker_container', '')
                    if dcname:
                        cmd = (f'docker exec {dcname} mysqldump -h{db_entry.get("host","127.0.0.1")}'
                               f' -u{db_entry.get("user","root")} -p{db_entry.get("password","")}'
                               f' --single-transaction --routines --triggers {db_name} 2>/dev/null')
                    else:
                        cmd = (f'mysqldump -h{db_entry.get("host","127.0.0.1")} -P{db_entry.get("port",3306)}'
                               f' -u{db_entry.get("user","root")} -p{db_entry.get("password","")}'
                               f' --single-transaction --routines --triggers {db_name} 2>/dev/null')
                    local_dump = os.path.join(db_dir, f'mysql_{db_name}.sql.gz')
                    rc = _stream_remote(ssh, f'{cmd} | gzip -c', local_dump)
                    sz = os.path.getsize(local_dump) if os.path.exists(local_dump) else 0
                    _log(state, f"    {'✓' if rc == 0 else '✗'} {human_size(sz)}")
                    manifest['targets']['databases']['dumps'].append(
                        {'type': 'mysql', 'db': db_name, 'file': f'mysql_{db_name}.sql.gz', 'size': sz, 'ok': rc == 0})

                for db_entry in backup.get('databases', {}).get('postgres', []):
                    db_name = db_entry.get('name', '')
                    _log(state, f"  PostgreSQL: {db_name}")
                    dcname = db_entry.get('docker_container', '')
                    pw     = db_entry.get('password', '')
                    if dcname:
                        cmd = (f'docker exec -e PGPASSWORD={pw} {dcname}'
                               f' pg_dump -h{db_entry.get("host","127.0.0.1")} -U{db_entry.get("user","postgres")} {db_name} 2>/dev/null')
                    else:
                        cmd = (f'PGPASSWORD={pw} pg_dump -h{db_entry.get("host","127.0.0.1")}'
                               f' -p{db_entry.get("port",5432)} -U{db_entry.get("user","postgres")} {db_name} 2>/dev/null')
                    local_dump = os.path.join(db_dir, f'pgsql_{db_name}.sql.gz')
                    rc = _stream_remote(ssh, f'{cmd} | gzip -c', local_dump)
                    sz = os.path.getsize(local_dump) if os.path.exists(local_dump) else 0
                    _log(state, f"    {'✓' if rc == 0 else '✗'} {human_size(sz)}")
                    manifest['targets']['databases']['dumps'].append(
                        {'type': 'postgres', 'db': db_name, 'file': f'pgsql_{db_name}.sql.gz', 'size': sz, 'ok': rc == 0})

            state['percent'] = 55

            # ── Sites web ─────────────────────────────────────────────────
            if 'websites' in targets:
                _log(state, "══ Backup sites web ══")
                web_dir = os.path.join(backup_path, 'websites')
                os.makedirs(web_dir, exist_ok=True)
                manifest['targets']['websites'] = {'archives': []}
                for wpath in backup.get('web_paths', ['/var/www/html']):
                    wpath = wpath.strip()
                    if not wpath: continue
                    _log(state, f"  {wpath}")
                    safe  = wpath.strip('/').replace('/', '_') + ext
                    excl  = f' {exclude_args}' if exclude_args else ''
                    cmd   = f'tar c{tar_flag}f - -C / {excl} "{wpath.lstrip("/")}" 2>/dev/null'
                    local_arc = os.path.join(web_dir, safe)
                    _stream_remote(ssh, cmd, local_arc)
                    sz = os.path.getsize(local_arc) if os.path.exists(local_arc) else 0
                    manifest['targets']['websites']['archives'].append({'path': wpath, 'file': safe, 'size': sz})
                    if verify:
                        ok = _verify_archive(local_arc, compression)
                        _log(state, f"    Vérif: {'✓' if ok else '✗ CORROMPU'}")

            state['percent'] = 75

            # ── Configurations ────────────────────────────────────────────
            if 'configs' in targets:
                _log(state, "══ Backup configurations ══")
                cfg_dir = os.path.join(backup_path, 'configs')
                os.makedirs(cfg_dir, exist_ok=True)
                manifest['targets']['configs'] = {'archives': []}
                for cpath in backup.get('config_paths', ['/etc/nginx']):
                    cpath = cpath.strip()
                    if not cpath: continue
                    _log(state, f"  {cpath}")
                    safe      = cpath.strip('/').replace('/', '_') + ext
                    local_arc = os.path.join(cfg_dir, safe)
                    _stream_remote(ssh, f'tar c{tar_flag}f - -C / "{cpath.lstrip("/")}" 2>/dev/null', local_arc)
                    sz = os.path.getsize(local_arc) if os.path.exists(local_arc) else 0
                    manifest['targets']['configs']['archives'].append({'path': cpath, 'file': safe, 'size': sz})

            state['percent'] = 88
            ssh.close(); ssh = None

            # ── Post-hook ─────────────────────────────────────────────────
            post_hook = backup.get('post_hook', '').strip()
            if post_hook and HAS_PARAMIKO:
                ssh2 = _ssh_connect(remote)
                _log(state, f"Hook post-backup: {post_hook}")
                rc, out, err = _ssh_exec(ssh2, post_hook, timeout=120)
                _log(state, f"  Hook: {'OK' if rc == 0 else 'ERREUR'} {(out + err).strip()[:200]}")
                ssh2.close()

            # ── Rotation par nombre ────────────────────────────────────────
            bkp_root  = os.path.join(data_dir, 'backups', subdir)
            existing  = sorted([d for d in os.listdir(bkp_root) if os.path.isdir(os.path.join(bkp_root, d))])
            max_count = int(backup.get('max_count', 7))
            for old in existing[:-max_count] if len(existing) > max_count else []:
                _log(state, f"Rotation (count) → suppression: {old}")
                shutil.rmtree(os.path.join(bkp_root, old), ignore_errors=True)

            # ── Rotation par âge ──────────────────────────────────────────
            max_days = int(backup.get('max_days', 0))
            if max_days > 0:
                cutoff = datetime.now() - timedelta(days=max_days)
                for d in sorted([d for d in os.listdir(bkp_root) if os.path.isdir(os.path.join(bkp_root, d))]):
                    full_d = os.path.join(bkp_root, d)
                    if datetime.fromtimestamp(os.path.getmtime(full_d)) < cutoff:
                        _log(state, f"Rotation (âge >{max_days}j) → suppression: {d}")
                        shutil.rmtree(full_d, ignore_errors=True)

            # ── Manifest ──────────────────────────────────────────────────
            manifest['finished_at'] = datetime.now().isoformat()
            manifest['status']      = 'ok'
            manifest['backup_path'] = backup_path
            with open(os.path.join(backup_path, 'manifest.json'), 'w') as f:
                json.dump(manifest, f, indent=2)
            state['last_manifest'] = manifest
            state['last_status']   = 'ok'
            state['percent']       = 100
            _log(state, "✓ Backup terminé avec succès")

            webhook = backup.get('webhook_url', '').strip()
            if webhook:
                total_size = sum(f.stat().st_size for f in Path(backup_path).rglob('*') if f.is_file())
                _notify(webhook, {
                    'event': 'backup_success', 'timestamp': manifest['finished_at'],
                    'remote_name': remote.get('name', ''), 'host': remote.get('host', ''),
                    'backup_id': ts, 'size': human_size(total_size)
                })

        except Exception as e:
            state['last_status']  = 'error'
            manifest['status']    = 'error'
            manifest['error']     = str(e)
            _log(state, f"✗ Erreur: {e}")
            if ssh:
                try: ssh.close()
                except Exception: pass
            webhook = remote.get('backup', {}).get('webhook_url', '').strip()
            if webhook:
                _notify(webhook, {'event': 'backup_error', 'error': str(e),
                                   'remote_name': remote.get('name', ''),
                                   'timestamp': datetime.now().isoformat()})
        finally:
            state['running'] = False

    threading.Thread(target=_run, daemon=True).start()
    return True, "Backup démarré"

# ─── Backup API ──────────────────────────────────────────────────────────────

@app.route('/api/backup/settings/<remote_id>', methods=['GET', 'POST'])
@login_required
def backup_settings(remote_id):
    c = load_config()
    remote_idx = next((i for i, r in enumerate(c.get('remotes', [])) if r.get('id') == remote_id), None)
    if remote_idx is None:
        return jsonify({'error': 'Remote introuvable'}), 404

    if request.method == 'GET':
        r = dict(c['remotes'][remote_idx])
        if r.get('password'): r['password'] = '**hidden**'
        bkp = dict(r.get('backup', {}))
        for kind in ('mysql', 'postgres'):
            for entry in bkp.get('databases', {}).get(kind, []):
                if entry.get('password'): entry['password'] = '**hidden**'
        r['backup'] = bkp
        return jsonify(r)

    if session.get('role') != 'admin':
        return jsonify({'error': 'Droits administrateur requis'}), 403

    d = request.json or {}
    r = c['remotes'][remote_idx]
    for key in ('name', 'host', 'user', 'auth_type', 'key_path', 'key_passphrase'):
        if key in d: r[key] = d[key]
    if 'port' in d: r['port'] = int(d['port'])
    if d.get('password') and d['password'] != '**hidden**': r['password'] = d['password']

    if 'backup' in d:
        backup = d['backup']
        for key in ('web_paths', 'config_paths', 'docker_names', 'excludes'):
            if key in backup:
                backup[key] = [str(p).strip() for p in backup[key] if str(p).strip()]
        existing_dbs = r.get('backup', {}).get('databases', {})
        for kind in ('mysql', 'postgres'):
            for i, entry in enumerate(backup.get('databases', {}).get(kind, [])):
                if entry.get('password') == '**hidden**':
                    existing = existing_dbs.get(kind) or []
                    entry['password'] = existing[i]['password'] if i < len(existing) else ''
        r['backup'] = backup

    c['remotes'][remote_idx] = r
    save_config(c)
    _apply_schedule()
    return jsonify({'ok': True})


@app.route('/api/backup/test/<remote_id>', methods=['POST'])
@login_required
def backup_test(remote_id):
    remote = _get_remote(remote_id)
    if not remote: return jsonify({'error': 'Remote introuvable'}), 404
    c  = load_config()
    r  = dict(remote)
    ov = request.json or {}
    if ov.get('host'):
        for k in ('host', 'port', 'user', 'auth_type', 'key_path', 'key_passphrase', 'password'):
            if k in ov: r[k] = ov[k]
    if r.get('password') == '**hidden**': r['password'] = remote.get('password', '')
    try:
        ssh = _ssh_connect(r)
        rc, out, err = _ssh_exec(ssh, 'hostname && uname -r && docker --version 2>/dev/null || echo "docker: non installé"', timeout=15)
        rc2, disk_out, _ = _ssh_exec(ssh, 'df -h / 2>/dev/null | tail -1', timeout=10)
        ssh.close()
        return jsonify({'ok': True, 'output': out.strip(), 'disk': disk_out.strip()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/backup/run/<remote_id>', methods=['POST'])
@admin_required
def backup_run(remote_id):
    ok, msg = run_backup(remote_id)
    return jsonify({'ok': ok, 'message': msg})


@app.route('/api/backup/status/<remote_id>')
@login_required
def backup_status(remote_id):
    s = _get_backup_state(remote_id)
    return jsonify({
        'running':       s.get('running', False),
        'progress':      s.get('progress', ''),
        'percent':       s.get('percent', 0),
        'last_run':      s.get('last_run'),
        'last_status':   s.get('last_status'),
        'log':           s.get('last_log', [])[-80:],
        'has_scheduler': HAS_SCHEDULER,
        'has_paramiko':  HAS_PARAMIKO,
    })


@app.route('/api/backup/list/<remote_id>')
@login_required
def backup_list(remote_id):
    remote = _get_remote(remote_id)
    if not remote: return jsonify({'error': 'Remote introuvable'}), 404
    try:
        backup   = remote.get('backup', {})
        subdir   = (backup.get('subdir', '') or remote_id).strip('/')
        bkp_root = os.path.join(get_data_dir(), 'backups', subdir)
        if not os.path.isdir(bkp_root): return jsonify({'backups': []})
        items = []
        for name in sorted(os.listdir(bkp_root), reverse=True):
            full = os.path.join(bkp_root, name)
            if not os.path.isdir(full): continue
            size  = sum(f.stat().st_size for f in Path(full).rglob('*') if f.is_file())
            mtime = datetime.fromtimestamp(os.path.getmtime(full)).strftime('%Y-%m-%d %H:%M')
            status = 'unknown'; targets_summary = ''
            mp = os.path.join(full, 'manifest.json')
            if os.path.exists(mp):
                try:
                    with open(mp) as f: m = json.load(f)
                    status = m.get('status', 'unknown')
                    targets_summary = ', '.join(m.get('targets', {}).keys())
                except Exception: pass
            items.append({'id': name, 'size': human_size(size), 'size_bytes': size,
                           'mtime': mtime, 'status': status, 'targets': targets_summary})
        return jsonify({'backups': items})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/backup/manifest/<remote_id>/<bkp_id>')
@login_required
def backup_manifest(remote_id, bkp_id):
    if '/' in bkp_id or bkp_id.startswith('.'): return jsonify({'error': 'ID invalide'}), 400
    remote = _get_remote(remote_id)
    if not remote: return jsonify({'error': 'Remote introuvable'}), 404
    subdir = (remote.get('backup', {}).get('subdir', '') or remote_id).strip('/')
    path   = os.path.join(get_data_dir(), 'backups', subdir, bkp_id, 'manifest.json')
    if not os.path.exists(path): return jsonify({'error': 'Manifest introuvable'}), 404
    try:
        with open(path) as f: return jsonify(json.load(f))
    except Exception as e: return jsonify({'error': str(e)}), 500


@app.route('/api/backup/contents/<remote_id>/<bkp_id>')
@login_required
def backup_contents(remote_id, bkp_id):
    if '/' in bkp_id or bkp_id.startswith('.'): return jsonify({'error': 'ID invalide'}), 400
    remote = _get_remote(remote_id)
    if not remote: return jsonify({'error': 'Remote introuvable'}), 404
    subdir   = (remote.get('backup', {}).get('subdir', '') or remote_id).strip('/')
    bkp_root = os.path.realpath(os.path.join(get_data_dir(), 'backups', subdir))
    bkp_dir  = os.path.realpath(os.path.join(bkp_root, bkp_id))
    if not bkp_dir.startswith(bkp_root + os.sep): return jsonify({'error': 'Chemin invalide'}), 403
    if not os.path.isdir(bkp_dir): return jsonify({'error': 'Introuvable'}), 404
    files = []
    for f in sorted(Path(bkp_dir).rglob('*')):
        if f.is_file():
            rel = str(f.relative_to(bkp_dir))
            files.append({'path': rel, 'size': human_size(f.stat().st_size), 'size_bytes': f.stat().st_size})
    return jsonify({'files': files, 'count': len(files)})


@app.route('/api/backup/restore/<remote_id>', methods=['POST'])
@admin_required
def backup_restore(remote_id):
    remote = _get_remote(remote_id)
    if not remote: return jsonify({'error': 'Remote introuvable'}), 404
    d        = request.json or {}
    bkp_id   = d.get('backup_id', '').strip()
    arc_path = d.get('archive', '').strip()
    dest     = d.get('dest', '/tmp/restore').strip()
    if '/' in bkp_id or bkp_id.startswith('.') or '..' in arc_path:
        return jsonify({'error': 'Paramètre invalide'}), 400
    try:
        subdir   = (remote.get('backup', {}).get('subdir', '') or remote_id).strip('/')
        local_arc = os.path.realpath(os.path.join(get_data_dir(), 'backups', subdir, bkp_id, arc_path))
        base      = os.path.realpath(os.path.join(get_data_dir(), 'backups', subdir, bkp_id))
        if not local_arc.startswith(base + os.sep): return jsonify({'error': 'Chemin invalide'}), 403
        if not os.path.isfile(local_arc):           return jsonify({'error': 'Archive introuvable'}), 404
        flags = 'xzf' if local_arc.endswith('.tar.gz') else ('xjf' if local_arc.endswith('.tar.bz2') else 'xf')
        ssh = _ssh_connect(remote)
        _ssh_exec(ssh, f'mkdir -p "{dest}"', timeout=10)
        transport = ssh.get_transport()
        chan = transport.open_session()
        chan.exec_command(f'tar {flags} - -C "{dest}"')
        with open(local_arc, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk: break
                chan.sendall(chunk)
        chan.shutdown_write()
        rc         = chan.recv_exit_status()
        stderr_out = chan.recv_stderr(4096).decode('utf-8', errors='replace')
        chan.close(); ssh.close()
        return jsonify({'ok': rc == 0,
                        'message': f'Restauré dans {dest}' if rc == 0 else f'Erreur restauration (rc={rc})',
                        'stderr': stderr_out.strip()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/backup/delete/<remote_id>', methods=['POST'])
@admin_required
def backup_delete(remote_id):
    bkp_id = (request.json or {}).get('id', '').strip()
    if not bkp_id or '/' in bkp_id or bkp_id.startswith('.'): return jsonify({'error': 'ID invalide'}), 400
    remote = _get_remote(remote_id)
    if not remote: return jsonify({'error': 'Remote introuvable'}), 404
    subdir   = (remote.get('backup', {}).get('subdir', '') or remote_id).strip('/')
    bkp_root = os.path.realpath(os.path.join(get_data_dir(), 'backups', subdir))
    target   = os.path.realpath(os.path.join(bkp_root, bkp_id))
    if not target.startswith(bkp_root + os.sep): return jsonify({'error': 'Chemin invalide'}), 403
    if not os.path.isdir(target): return jsonify({'error': 'Introuvable'}), 404
    try:
        shutil.rmtree(target)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/backup/docker-containers/<remote_id>', methods=['POST'])
@login_required
def backup_docker_containers(remote_id):
    remote = _get_remote(remote_id)
    if not remote: return jsonify({'ok': False, 'error': 'Remote introuvable'})
    try:
        ssh = _ssh_connect(remote)
        rc, out, _ = _ssh_exec(ssh, 'docker ps --format "{{.Names}}|{{.Image}}|{{.Status}}"', timeout=15)
        ssh.close()
        containers = []
        for line in out.splitlines():
            parts = line.split('|')
            if parts:
                containers.append({'name': parts[0].strip(),
                                    'image': parts[1].strip() if len(parts) > 1 else '',
                                    'status': parts[2].strip() if len(parts) > 2 else ''})
        return jsonify({'ok': True, 'containers': containers})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ─── WebSocket Terminal ───────────────────────────────────────────────────────

if HAS_SOCK:
    @sock.route('/ws/terminal/<remote_id>')
    def terminal_ws(ws, remote_id):
        if not session.get('logged_in'):
            try: ws.send('\r\n[Non autorisé]\r\n'); ws.close()
            except Exception: pass
            return

        remote = _get_remote(remote_id)
        if not remote:
            try: ws.send('\r\n[Remote introuvable]\r\n'); ws.close()
            except Exception: pass
            return

        ssh = None; chan = None
        try:
            ssh  = _ssh_connect(remote)
            chan = ssh.invoke_shell(term='xterm-256color', width=120, height=40)
            chan.settimeout(0.1)

            def read_remote():
                try:
                    while not chan.closed:
                        try:
                            data = chan.recv(4096)
                            if not data: break
                            ws.send(data.decode('utf-8', errors='replace'))
                        except Exception:
                            break
                finally:
                    try: ws.close()
                    except Exception: pass

            threading.Thread(target=read_remote, daemon=True).start()

            while True:
                try:
                    msg = ws.receive()
                    if msg is None: break
                    if isinstance(msg, str) and msg.startswith('{'):
                        try:
                            d = json.loads(msg)
                            if d.get('type') == 'resize':
                                chan.resize_pty(width=int(d.get('cols', 80)), height=int(d.get('rows', 24)))
                            continue
                        except Exception: pass
                    chan.sendall(msg.encode('utf-8') if isinstance(msg, str) else msg)
                except Exception:
                    break
        except Exception as e:
            try: ws.send(f'\r\n\033[31m[Erreur: {e}]\033[0m\r\n'); ws.close()
            except Exception: pass
        finally:
            if chan:
                try: chan.close()
                except Exception: pass
            if ssh:
                try: ssh.close()
                except Exception: pass

# ─── Entrypoint ──────────────────────────────────────────────────────────────

_apply_schedule()

if __name__ == '__main__':
    c    = load_config()
    port = int(os.environ.get('PORT', c.get('port', 5080)))
    app.run(host='::', port=port, debug=False, threaded=True)
