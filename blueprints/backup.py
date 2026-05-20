"""Routes API backup — /api/backup/*"""
import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, session

from blueprints.auth import login_required, admin_required
from core.config import load_config, save_config, get_data_dir, get_remote
from core.helpers import human_size
from core.backup_core import (
    ssh_connect, ssh_exec,
    get_backup_state, apply_schedule, run_backup,
    HAS_PARAMIKO, HAS_SCHEDULER,
)

backup_bp = Blueprint('backup', __name__)


@backup_bp.route('/api/backup/settings/<remote_id>', methods=['GET', 'POST'])
@login_required
def backup_settings(remote_id):
    c = load_config()
    remote_idx = next((i for i, r in enumerate(c.get('remotes', [])) if r.get('id') == remote_id), None)
    if remote_idx is None:
        return jsonify({'error': 'Remote introuvable'}), 404

    if request.method == 'GET':
        r   = dict(c['remotes'][remote_idx])
        if r.get('password'):
            r['password'] = '**hidden**'
        bkp = dict(r.get('backup', {}))
        for kind in ('mysql', 'postgres'):
            for entry in bkp.get('databases', {}).get(kind, []):
                if entry.get('password'):
                    entry['password'] = '**hidden**'
        r['backup'] = bkp
        return jsonify(r)

    if session.get('role') != 'admin':
        return jsonify({'error': 'Droits administrateur requis'}), 403

    d = request.json or {}
    r = c['remotes'][remote_idx]
    for key in ('name', 'host', 'user', 'auth_type', 'key_path', 'key_passphrase'):
        if key in d:
            r[key] = d[key]
    if 'port' in d:
        r['port'] = int(d['port'])
    if d.get('password') and d['password'] != '**hidden**':
        r['password'] = d['password']

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
    apply_schedule()
    return jsonify({'ok': True})


@backup_bp.route('/api/backup/test/<remote_id>', methods=['POST'])
@login_required
def backup_test(remote_id):
    remote = get_remote(remote_id)
    if not remote:
        return jsonify({'error': 'Remote introuvable'}), 404
    r  = dict(remote)
    ov = request.json or {}
    if ov.get('host'):
        for k in ('host', 'port', 'user', 'auth_type', 'key_path', 'key_passphrase', 'password'):
            if k in ov:
                r[k] = ov[k]
    if r.get('password') == '**hidden**':
        r['password'] = remote.get('password', '')
    try:
        ssh = ssh_connect(r)
        rc, out, err = ssh_exec(ssh, 'hostname && uname -r && docker --version 2>/dev/null || echo "docker: non installé"', timeout=15)
        rc2, disk_out, _ = ssh_exec(ssh, 'df -h / 2>/dev/null | tail -1', timeout=10)
        ssh.close()
        return jsonify({'ok': True, 'output': out.strip(), 'disk': disk_out.strip()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@backup_bp.route('/api/backup/run/<remote_id>', methods=['POST'])
@admin_required
def backup_run(remote_id):
    ok, msg = run_backup(remote_id)
    return jsonify({'ok': ok, 'message': msg})


@backup_bp.route('/api/backup/status/<remote_id>')
@login_required
def backup_status(remote_id):
    s = get_backup_state(remote_id)
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


@backup_bp.route('/api/backup/list/<remote_id>')
@login_required
def backup_list(remote_id):
    remote = get_remote(remote_id)
    if not remote:
        return jsonify({'error': 'Remote introuvable'}), 404
    try:
        backup   = remote.get('backup', {})
        subdir   = (backup.get('subdir', '') or remote_id).strip('/')
        bkp_root = os.path.join(get_data_dir(), 'backups', subdir)
        if not os.path.isdir(bkp_root):
            return jsonify({'backups': []})
        items = []
        for name in sorted(os.listdir(bkp_root), reverse=True):
            full = os.path.join(bkp_root, name)
            if not os.path.isdir(full):
                continue
            size    = sum(f.stat().st_size for f in Path(full).rglob('*') if f.is_file())
            mtime   = datetime.fromtimestamp(os.path.getmtime(full)).strftime('%Y-%m-%d %H:%M')
            status  = 'unknown'
            targets_summary = ''
            mp = os.path.join(full, 'manifest.json')
            if os.path.exists(mp):
                try:
                    with open(mp) as f:
                        m = json.load(f)
                    status          = m.get('status', 'unknown')
                    targets_summary = ', '.join(m.get('targets', {}).keys())
                except Exception:
                    pass
            items.append({'id': name, 'size': human_size(size), 'size_bytes': size,
                           'mtime': mtime, 'status': status, 'targets': targets_summary})
        return jsonify({'backups': items})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@backup_bp.route('/api/backup/manifest/<remote_id>/<bkp_id>')
@login_required
def backup_manifest(remote_id, bkp_id):
    if '/' in bkp_id or bkp_id.startswith('.'):
        return jsonify({'error': 'ID invalide'}), 400
    remote = get_remote(remote_id)
    if not remote:
        return jsonify({'error': 'Remote introuvable'}), 404
    subdir = (remote.get('backup', {}).get('subdir', '') or remote_id).strip('/')
    path   = os.path.join(get_data_dir(), 'backups', subdir, bkp_id, 'manifest.json')
    if not os.path.exists(path):
        return jsonify({'error': 'Manifest introuvable'}), 404
    try:
        with open(path) as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@backup_bp.route('/api/backup/contents/<remote_id>/<bkp_id>')
@login_required
def backup_contents(remote_id, bkp_id):
    if '/' in bkp_id or bkp_id.startswith('.'):
        return jsonify({'error': 'ID invalide'}), 400
    remote = get_remote(remote_id)
    if not remote:
        return jsonify({'error': 'Remote introuvable'}), 404
    subdir   = (remote.get('backup', {}).get('subdir', '') or remote_id).strip('/')
    bkp_root = os.path.realpath(os.path.join(get_data_dir(), 'backups', subdir))
    bkp_dir  = os.path.realpath(os.path.join(bkp_root, bkp_id))
    if not bkp_dir.startswith(bkp_root + os.sep):
        return jsonify({'error': 'Chemin invalide'}), 403
    if not os.path.isdir(bkp_dir):
        return jsonify({'error': 'Introuvable'}), 404
    files = []
    for f in sorted(Path(bkp_dir).rglob('*')):
        if f.is_file():
            rel = str(f.relative_to(bkp_dir))
            files.append({'path': rel, 'size': human_size(f.stat().st_size), 'size_bytes': f.stat().st_size})
    return jsonify({'files': files, 'count': len(files)})


@backup_bp.route('/api/backup/restore/<remote_id>', methods=['POST'])
@admin_required
def backup_restore(remote_id):
    remote = get_remote(remote_id)
    if not remote:
        return jsonify({'error': 'Remote introuvable'}), 404
    d        = request.json or {}
    bkp_id   = d.get('backup_id', '').strip()
    arc_path = d.get('archive', '').strip()
    dest     = d.get('dest', '/tmp/restore').strip()
    if '/' in bkp_id or bkp_id.startswith('.') or '..' in arc_path:
        return jsonify({'error': 'Paramètre invalide'}), 400
    try:
        subdir    = (remote.get('backup', {}).get('subdir', '') or remote_id).strip('/')
        local_arc = os.path.realpath(os.path.join(get_data_dir(), 'backups', subdir, bkp_id, arc_path))
        base      = os.path.realpath(os.path.join(get_data_dir(), 'backups', subdir, bkp_id))
        if not local_arc.startswith(base + os.sep):
            return jsonify({'error': 'Chemin invalide'}), 403
        if not os.path.isfile(local_arc):
            return jsonify({'error': 'Archive introuvable'}), 404
        flags = 'xzf' if local_arc.endswith('.tar.gz') else ('xjf' if local_arc.endswith('.tar.bz2') else 'xf')
        ssh = ssh_connect(remote)
        ssh_exec(ssh, f'mkdir -p "{dest}"', timeout=10)
        transport = ssh.get_transport()
        chan = transport.open_session()
        chan.exec_command(f'tar {flags} - -C "{dest}"')
        with open(local_arc, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                chan.sendall(chunk)
        chan.shutdown_write()
        rc         = chan.recv_exit_status()
        stderr_out = chan.recv_stderr(4096).decode('utf-8', errors='replace')
        chan.close()
        ssh.close()
        return jsonify({'ok': rc == 0,
                        'message': f'Restauré dans {dest}' if rc == 0 else f'Erreur restauration (rc={rc})',
                        'stderr': stderr_out.strip()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@backup_bp.route('/api/backup/delete/<remote_id>', methods=['POST'])
@admin_required
def backup_delete(remote_id):
    bkp_id = (request.json or {}).get('id', '').strip()
    if not bkp_id or '/' in bkp_id or bkp_id.startswith('.'):
        return jsonify({'error': 'ID invalide'}), 400
    remote = get_remote(remote_id)
    if not remote:
        return jsonify({'error': 'Remote introuvable'}), 404
    subdir   = (remote.get('backup', {}).get('subdir', '') or remote_id).strip('/')
    bkp_root = os.path.realpath(os.path.join(get_data_dir(), 'backups', subdir))
    target   = os.path.realpath(os.path.join(bkp_root, bkp_id))
    if not target.startswith(bkp_root + os.sep):
        return jsonify({'error': 'Chemin invalide'}), 403
    if not os.path.isdir(target):
        return jsonify({'error': 'Introuvable'}), 404
    try:
        shutil.rmtree(target)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@backup_bp.route('/api/backup/docker-containers/<remote_id>', methods=['POST'])
@login_required
def backup_docker_containers(remote_id):
    remote = get_remote(remote_id)
    if not remote:
        return jsonify({'ok': False, 'error': 'Remote introuvable'})
    try:
        ssh = ssh_connect(remote)
        rc, out, _ = ssh_exec(ssh, 'docker ps --format "{{.Names}}|{{.Image}}|{{.Status}}"', timeout=15)
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