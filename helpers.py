"""Fonctions utilitaires partagées."""
import re, subprocess, hashlib


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


def setup_data_access(username: str) -> None:
    from config import get_data_dir
    data_dir = get_data_dir()
    run(['groupadd',  '-f',  'nxslab-data'])
    run(['chgrp',  'nxslab-data', data_dir])
    run(['chmod',  '2775',        data_dir])
    run(['usermod', '-a', '-G', 'nxslab-data', username])


def human_size(n):
    n = float(n)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(n) < 1024.0 or unit == 'TB':
            return f"{int(n)} B" if unit == 'B' else f"{n:.1f} {unit}"
        n /= 1024.0
