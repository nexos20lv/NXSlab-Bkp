"""Routes remotes CRUD + stats — /api/remotes/* /api/remote/<id>/stats /api/backup/history"""
import os
import re
import json
import uuid
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, session

from blueprints.auth import login_required, admin_required
from core.config import load_config, save_config, get_data_dir, get_remote
from core.helpers import human_size
from core.backup_core import (
    ssh_connect, ssh_exec,
    get_backup_state, next_cron_run, apply_schedule,
)

remotes_bp = Blueprint('remotes', __name__)


@remotes_bp.route('/api/remotes')
@login_required
def remotes_list():
    c = load_config()
    result = []
    for r in c.get('remotes', []):
        entry = {k: v for k, v in r.items() if k not in ('password', 'key_passphrase', 'backup')}
        if r.get('password'):
            entry['password'] = '**hidden**'
        state = get_backup_state(r.get('id', ''))
        entry['last_run']    = state.get('last_run')
        entry['last_status'] = state.get('last_status')
        entry['running']     = state.get('running', False)
        bkp     = r.get('backup', {})
        enabled = bool(bkp.get('schedule_enabled'))
        entry['schedule_enabled'] = enabled
        entry['schedule']         = bkp.get('schedule', '')
        entry['next_run']         = next_cron_run(bkp.get('schedule', '')) if enabled else None
        result.append(entry)
    return jsonify({'remotes': result})


@remotes_bp.route('/api/remotes/add', methods=['POST'])
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
    apply_schedule()
    return jsonify({'ok': True, 'id': new_id})


@remotes_bp.route('/api/remotes/update', methods=['POST'])
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
            apply_schedule()
            return jsonify({'ok': True})
    return jsonify({'error': 'Remote introuvable'}), 404


@remotes_bp.route('/api/remotes/delete', methods=['POST'])
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
    apply_schedule()
    return jsonify({'ok': True})


@remotes_bp.route('/api/remote/<remote_id>/stats')
@login_required
def remote_stats(remote_id):
    remote = get_remote(remote_id)
    if not remote:
        return jsonify({'error': 'Remote introuvable'}), 404
    try:
        ssh = ssh_connect(remote)
        _, cpu_out,  _ = ssh_exec(ssh, "top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'", timeout=10)
        _, mem_out,  _ = ssh_exec(ssh, "free -m | awk 'NR==2{print $2,$3,$4}'",            timeout=10)
        _, disk_out, _ = ssh_exec(ssh,
            "df -h --output=source,size,used,avail,pcent,target 2>/dev/null | grep -v tmpfs | grep -v udev | grep -v Filesystem",
            timeout=10)
        _, load_out, _ = ssh_exec(ssh, 'cat /proc/loadavg', timeout=10)
        _, up_out,   _ = ssh_exec(ssh, 'uptime -p',          timeout=10)
        _, dock_out, _ = ssh_exec(ssh,
            'docker ps --format "{{.Names}}|{{.Status}}" 2>/dev/null | head -30',
            timeout=10)
        _, kern_out, _ = ssh_exec(ssh, 'uname -r', timeout=5)
        ssh.close()

        m       = mem_out.strip().split()
        total   = int(m[0]) if m else 0
        used    = int(m[1]) if len(m) > 1 else 0
        mem_pct = round((used / total) * 100) if total else 0

        disks = []
        for line in disk_out.strip().splitlines():
            p = line.split()
            if len(p) >= 6:
                try:
                    pct_int = int(p[4].replace('%', ''))
                except Exception:
                    pct_int = 0
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


@remotes_bp.route('/api/backup/history')
@login_required
def backup_history():
    c        = load_config()
    data_dir = get_data_dir()
    result   = {}
    for remote in c.get('remotes', []):
        rid      = remote.get('id', '')
        subdir   = (remote.get('backup', {}).get('subdir', '') or rid).strip('/')
        bkp_root = os.path.join(data_dir, 'backups', subdir)
        points   = []
        if os.path.isdir(bkp_root):
            for name in sorted(os.listdir(bkp_root)):
                full = os.path.join(bkp_root, name)
                if not os.path.isdir(full):
                    continue
                size   = sum(f.stat().st_size for f in Path(full).rglob('*') if f.is_file())
                mtime  = datetime.fromtimestamp(os.path.getmtime(full)).strftime('%Y-%m-%d %H:%M')
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