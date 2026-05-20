"""Routes système — /health /api/status /api/system /api/logs/*"""
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from blueprints.auth import login_required
from core.config import load_config, get_data_dir, APP_START
from core.helpers import svc_state, shell

system_bp = Blueprint('system', __name__)


@system_bp.route('/health')
def health():
    from core.backup_core import get_backup_state, HAS_PARAMIKO, HAS_SCHEDULER
    import flask
    c          = load_config()
    uptime_sec = int((datetime.now() - APP_START).total_seconds())
    remotes_status = []
    for r in c.get('remotes', []):
        rid   = r.get('id', '')
        state = get_backup_state(rid)
        remotes_status.append({
            'id':          rid,
            'name':        r.get('name', ''),
            'host':        r.get('host', ''),
            'last_backup': state.get('last_run'),
            'last_status': state.get('last_status'),
        })
    return jsonify({
        'status':         'ok',
        'version':        '2.1.0',
        'uptime_seconds': uptime_sec,
        'services':       {'samba': svc_state('smbd'), 'ftp': svc_state('vsftpd')},
        'remotes':        remotes_status,
        'has_paramiko':   HAS_PARAMIKO,
        'has_scheduler':  HAS_SCHEDULER,
        'has_websocket':  flask.current_app.config.get('HAS_SOCK', False),
    })


@system_bp.route('/api/status')
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
        'data_dir':  get_data_dir(),
    })


@system_bp.route('/api/system')
@login_required
def api_system():
    disk_r = shell("df -h --output=source,size,used,avail,pcent,target 2>/dev/null | grep -v tmpfs | grep -v udev | grep -v Filesystem")
    disks  = []
    for line in disk_r['out'].splitlines():
        p = line.split()
        if len(p) >= 6:
            try:    pct_int = int(p[4].replace('%', ''))
            except: pct_int = 0
            disks.append({'device': p[0], 'size': p[1], 'used': p[2], 'avail': p[3],
                          'percent': p[4], 'percent_int': pct_int, 'mount': p[5]})
    mem_r = shell("free -m | awk 'NR==2{print $2,$3,$4}'")
    m     = mem_r['out'].strip().split()
    total = int(m[0]) if m else 0
    used  = int(m[1]) if len(m) > 1 else 0
    free  = int(m[2]) if len(m) > 2 else 0
    mem_pct = round((used / total) * 100) if total else 0
    cpu_r   = shell("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'")
    load_r  = shell('cat /proc/loadavg')
    lp      = load_r['out'].split()
    return jsonify({
        'disks':  disks,
        'memory': {'total': total, 'used': used, 'free': free, 'percent': mem_pct},
        'cpu':    cpu_r['out'].strip() or '0',
        'load':   {'1m': lp[0] if lp else '0', '5m': lp[1] if len(lp) > 1 else '0', '15m': lp[2] if len(lp) > 2 else '0'},
        'uptime': shell('uptime -p')['out'].strip()
    })


@system_bp.route('/api/logs/<service>')
@login_required
def api_logs(service):
    allowed = ('samba', 'ftp', 'nxslab', 'system', 'auth', 'kernel', 'docker')
    if service not in allowed:
        return jsonify({'error': 'Service inconnu'}), 400
    lines = min(int(request.args.get('lines', 100)), 500)
    cmds = {
        'samba':  f'journalctl -u smbd -n {lines} --no-pager --output=short-iso 2>/dev/null || tail -n {lines} /var/log/samba/log.smbd 2>/dev/null',
        'ftp':    f'journalctl -u vsftpd -n {lines} --no-pager --output=short-iso 2>/dev/null || tail -n {lines} /var/log/vsftpd.log 2>/dev/null',
        'nxslab': f'journalctl -u nxslab-bkp -n {lines} --no-pager --output=short-iso 2>/dev/null',
        'system': f'journalctl -n {lines} --no-pager --output=short-iso 2>/dev/null',
        'auth':   f'journalctl _COMM=sshd _COMM=sudo _COMM=su -n {lines} --no-pager --output=short-iso 2>/dev/null || tail -n {lines} /var/log/auth.log 2>/dev/null',
        'kernel': f'journalctl -k -n {lines} --no-pager --output=short-iso 2>/dev/null || dmesg -T 2>/dev/null | tail -n {lines}',
        'docker': f'journalctl -u docker -n {lines} --no-pager --output=short-iso 2>/dev/null || tail -n {lines} /var/log/docker.log 2>/dev/null',
    }
    r = shell(cmds[service])
    return jsonify({'logs': r['out'] or '(aucun journal disponible)', 'err': r['err'] if not r['ok'] else ''})