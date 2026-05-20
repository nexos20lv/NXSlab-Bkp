"""Configuration — chargement, sauvegarde, migration."""
import os, json, hashlib, secrets, uuid
from datetime import datetime

CONFIG_FILE = os.environ.get('CONFIG_FILE', '/etc/nxslab-bkp/config.json')
APP_START   = datetime.now()


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
    if 'username' in c and 'users' not in c:
        c['users'] = [{'username': c.pop('username'), 'password_hash': c.pop('password_hash', ''), 'role': 'admin'}]
        changed = True
    elif 'users' not in c:
        c['users'] = [{'username': 'admin', 'password_hash': hashlib.sha256(b'admin').hexdigest(), 'role': 'admin'}]
        changed = True
    for u in c.get('users', []):
        if 'role' not in u:
            u['role'] = 'admin'
            changed = True
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


def get_data_dir():
    return load_config().get('data_dir', '/srv/nxslab-bkp')


def get_remote(remote_id: str):
    for r in load_config().get('remotes', []):
        if r.get('id') == remote_id:
            return r
    return None