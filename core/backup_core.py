"""Moteur de backup SSH — helpers, état, scheduler, run_backup()"""
import os
import json
import shutil
import subprocess
import threading
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

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
    _scheduler   = None
    HAS_SCHEDULER = False

from core.config import load_config, get_data_dir, get_remote
from core.helpers import human_size


def ssh_connect(remote: dict):
    if not HAS_PARAMIKO:
        raise RuntimeError("paramiko non installé — lancez: pip install paramiko")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    host = remote.get('host', '').strip()
    if not host:
        raise ValueError("Hôte VPS distant non configuré")
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


def ssh_exec(ssh, cmd: str, timeout: int = 300):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    rc  = stdout.channel.recv_exit_status()
    return rc, out, err


def stream_remote(ssh, remote_cmd: str, local_path: str) -> int:
    transport = ssh.get_transport()
    chan = transport.open_session()
    chan.exec_command(remote_cmd)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, 'wb') as f:
        while True:
            chunk = chan.recv(65536)
            if not chunk:
                break
            f.write(chunk)
    rc = chan.recv_exit_status()
    chan.close()
    return rc


def verify_archive(local_path: str, compression: str) -> bool:
    if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
        return False
    flag_map = {'gz': 'z', 'bz2': 'j', 'none': ''}
    f = flag_map.get(compression, 'z')
    result = subprocess.run(['tar', f't{f}f', local_path], capture_output=True, timeout=60)
    return result.returncode == 0


def notify(url: str, payload: dict):
    if not url:
        return
    # NXS-SEC-010: only deliver to http(s) webhooks. urllib would otherwise honor
    # file://, ftp://, gopher://, dict://, ... turning a webhook field into an
    # SSRF / local-resource primitive.
    if urllib.parse.urlparse(url).scheme.lower() not in ('http', 'https'):
        return
    try:
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            url, data=data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'NXSlab-Bkp/2.1'},
            method='POST')
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def next_cron_run(schedule: str):
    if not HAS_SCHEDULER or not schedule:
        return None
    try:
        from datetime import timezone
        parts = schedule.strip().split()
        if len(parts) != 5:
            return None
        trigger = CronTrigger(
            minute=parts[0], hour=parts[1],
            day=parts[2], month=parts[3], day_of_week=parts[4]
        )
        nxt = trigger.get_next_fire_time(None, datetime.now(tz=timezone.utc))
        return nxt.astimezone().strftime('%Y-%m-%d %H:%M') if nxt else None
    except Exception:
        return None


_backup_states: dict = {}
_backup_locks:  dict = {}


def get_backup_state(remote_id: str) -> dict:
    if remote_id not in _backup_states:
        _backup_states[remote_id] = {
            'running': False, 'progress': '', 'percent': 0,
            'last_run': None, 'last_status': None, 'last_log': [],
            'last_manifest': None
        }
    return _backup_states[remote_id]


def get_backup_lock(remote_id: str) -> threading.Lock:
    if remote_id not in _backup_locks:
        _backup_locks[remote_id] = threading.Lock()
    return _backup_locks[remote_id]


def _log(state: dict, msg: str):
    ts = datetime.now().strftime('%H:%M:%S')
    state['last_log'].append(f"[{ts}] {msg}")
    state['progress'] = msg


def apply_schedule():
    if not HAS_SCHEDULER:
        return
    try:
        _scheduler.remove_all_jobs()
        for remote in load_config().get('remotes', []):
            rid    = remote.get('id', '')
            backup = remote.get('backup', {})
            if backup.get('schedule_enabled') and backup.get('schedule'):
                parts = backup['schedule'].split()
                if len(parts) == 5:
                    _scheduler.add_job(
                        lambda r=rid: run_backup(r) if not get_backup_state(r).get('running') else None,
                        CronTrigger(minute=parts[0], hour=parts[1],
                                    day=parts[2], month=parts[3], day_of_week=parts[4]),
                        id=f'backup_{rid}', replace_existing=True
                    )
    except Exception:
        pass


def run_backup(remote_id: str):
    remote = get_remote(remote_id)
    if not remote:
        return False, "Remote introuvable"

    state = get_backup_state(remote_id)
    with get_backup_lock(remote_id):
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
            do_verify    = backup.get('verify', False)
            exclude_args = ' '.join(f'--exclude="{e}"' for e in backup.get('excludes', []) if e.strip())

            pre_hook = backup.get('pre_hook', '').strip()
            if pre_hook:
                _log(state, f"Hook pré-backup: {pre_hook}")
            state['percent'] = 2

            _log(state, f"Connexion SSH → {remote.get('host', '?')}:{remote.get('port', 22)}")
            ssh = ssh_connect(remote)
            _log(state, "Connexion établie")
            state['percent'] = 5

            if pre_hook:
                rc, out, err = ssh_exec(ssh, pre_hook, timeout=120)
                _log(state, f"  Hook: {'OK' if rc == 0 else 'ERREUR'} {(out + err).strip()[:200]}")

            targets = backup.get('targets', ['docker', 'websites', 'configs'])

            if 'docker' in targets:
                _log(state, "══ Backup Docker ══")
                state['percent'] = 10
                docker_dir = os.path.join(backup_path, 'docker')
                os.makedirs(docker_dir, exist_ok=True)
                manifest['targets']['docker'] = {'containers': {}}

                if backup.get('docker_all', True):
                    rc, out, _ = ssh_exec(ssh, 'docker ps --format "{{.Names}}"')
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
                        _log(state, f"    Arrêt {cname}...")
                        ssh_exec(ssh, f'docker stop {cname}', timeout=30)

                    rc, out, _ = ssh_exec(ssh, f'docker inspect {cname} 2>/dev/null')
                    if rc == 0 and out.strip():
                        with open(os.path.join(cdir, 'inspect.json'), 'w') as f:
                            f.write(out)

                    fmt = '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}|{{.Destination}}\n{{end}}{{end}}'
                    rc, out, _ = ssh_exec(ssh, f"docker inspect --format '{fmt}' {cname} 2>/dev/null")
                    for line in out.splitlines():
                        parts = line.strip().split('|')
                        if not parts or not parts[0]:
                            continue
                        vol_name  = parts[0]
                        local_vol = os.path.join(cdir, vol_name + ext)
                        _log(state, f"    Volume: {vol_name}")
                        cmd = f'docker run --rm -v {vol_name}:/bkp_vol:ro alpine tar c{tar_flag}f - -C /bkp_vol . 2>/dev/null'
                        rc2 = stream_remote(ssh, cmd, local_vol)
                        if rc2 != 0:
                            err_msg = f"Erreur volume {vol_name} (rc={rc2})"
                            _log(state, f"    ⚠ {err_msg}")
                            manifest['targets']['docker']['containers'][cname]['errors'].append(err_msg)
                        else:
                            sz = os.path.getsize(local_vol) if os.path.exists(local_vol) else 0
                            manifest['targets']['docker']['containers'][cname]['volumes'].append(
                                {'name': vol_name, 'file': vol_name + ext, 'size': sz})
                            if do_verify:
                                ok = verify_archive(local_vol, compression)
                                _log(state, f"    Vérif: {'✓' if ok else '✗ CORROMPU'}")
                                if not ok:
                                    manifest['errors'].append(f"Archive corrompue: {local_vol}")

                    fmt = '{{range .Mounts}}{{if eq .Type "bind"}}{{.Source}}|{{.Destination}}\n{{end}}{{end}}'
                    rc, out, _ = ssh_exec(ssh, f"docker inspect --format '{fmt}' {cname} 2>/dev/null")
                    for line in out.splitlines():
                        parts = line.strip().split('|')
                        if not parts or len(parts) < 2:
                            continue
                        src_path = parts[0]
                        dest_path = parts[1]
                        safe_name = dest_path.strip('/').replace('/', '_')
                        local_bind = os.path.join(cdir, safe_name + ext)
                        _log(state, f"    Bind: {src_path} → {dest_path}")

                        check_cmd = f'test -e "{src_path}" && echo exists || echo notfound'
                        rc_check, exists, _ = ssh_exec(ssh, check_cmd)
                        if exists.strip() != "exists":
                            continue

                        check_cmd = f'[ -f "{src_path}" ] && echo file || echo dir'
                        rc_type, type_out, _ = ssh_exec(ssh, check_cmd)
                        path_type = type_out.strip()

                        if path_type == "file":
                            cmd = f'cat "{src_path}" 2>/dev/null | gzip -c'
                        else:
                            cmd = f'tar c{tar_flag}f - -L --no-same-permissions --no-same-owner --ignore-failed-read -C "{src_path}" . 2>/dev/null || true'

                        rc2 = stream_remote(ssh, cmd, local_bind)
                        sz = os.path.getsize(local_bind) if os.path.exists(local_bind) else 0

                        if sz > 0:
                            manifest['targets']['docker']['containers'][cname]['volumes'].append(
                                {'name': f'bind:{dest_path}', 'source': src_path, 'file': safe_name + ext, 'size': sz, 'type': path_type})
                            _log(state, f"    ✓ {safe_name} ({human_size(sz)})")
                            if do_verify and path_type == "dir":
                                ok = verify_archive(local_bind, compression)
                                _log(state, f"    Vérif: {'✓' if ok else '✗ CORROMPU'}")
                                if not ok:
                                    manifest['errors'].append(f"Archive corrompue: {local_bind}")
                        else:
                            try:
                                os.remove(local_bind)
                            except Exception:
                                pass
                            _log(state, f"    ⊘ {safe_name} (vide ou inaccessible)")

                    if stop_before:
                        _log(state, f"    Redémarrage {cname}...")
                        ssh_exec(ssh, f'docker start {cname}', timeout=30)

            state['percent'] = 35

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
                    rc = stream_remote(ssh, f'{cmd} | gzip -c', local_dump)
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
                    rc = stream_remote(ssh, f'{cmd} | gzip -c', local_dump)
                    sz = os.path.getsize(local_dump) if os.path.exists(local_dump) else 0
                    _log(state, f"    {'✓' if rc == 0 else '✗'} {human_size(sz)}")
                    manifest['targets']['databases']['dumps'].append(
                        {'type': 'postgres', 'db': db_name, 'file': f'pgsql_{db_name}.sql.gz', 'size': sz, 'ok': rc == 0})

            state['percent'] = 55

            if 'websites' in targets:
                _log(state, "══ Backup sites web ══")
                web_dir = os.path.join(backup_path, 'websites')
                os.makedirs(web_dir, exist_ok=True)
                manifest['targets']['websites'] = {'archives': []}
                for wpath in backup.get('web_paths', ['/var/www/html']):
                    wpath = wpath.strip()
                    if not wpath:
                        continue
                    _log(state, f"  {wpath}")
                    safe      = wpath.strip('/').replace('/', '_') + ext
                    excl      = f' {exclude_args}' if exclude_args else ''
                    cmd       = f'tar c{tar_flag}f - -C / {excl} "{wpath.lstrip("/")}" 2>/dev/null'
                    local_arc = os.path.join(web_dir, safe)
                    stream_remote(ssh, cmd, local_arc)
                    sz = os.path.getsize(local_arc) if os.path.exists(local_arc) else 0
                    manifest['targets']['websites']['archives'].append({'path': wpath, 'file': safe, 'size': sz})
                    if do_verify:
                        ok = verify_archive(local_arc, compression)
                        _log(state, f"    Vérif: {'✓' if ok else '✗ CORROMPU'}")

            state['percent'] = 75

            if 'configs' in targets:
                _log(state, "══ Backup configurations ══")
                cfg_dir = os.path.join(backup_path, 'configs')
                os.makedirs(cfg_dir, exist_ok=True)
                manifest['targets']['configs'] = {'archives': []}
                for cpath in backup.get('config_paths', ['/etc/nginx']):
                    cpath = cpath.strip()
                    if not cpath:
                        continue
                    _log(state, f"  {cpath}")
                    safe      = cpath.strip('/').replace('/', '_') + ext
                    local_arc = os.path.join(cfg_dir, safe)
                    stream_remote(ssh, f'tar c{tar_flag}f - -C / "{cpath.lstrip("/")}" 2>/dev/null', local_arc)
                    sz = os.path.getsize(local_arc) if os.path.exists(local_arc) else 0
                    manifest['targets']['configs']['archives'].append({'path': cpath, 'file': safe, 'size': sz})

            state['percent'] = 88
            ssh.close()
            ssh = None

            post_hook = backup.get('post_hook', '').strip()
            if post_hook and HAS_PARAMIKO:
                ssh2 = ssh_connect(remote)
                _log(state, f"Hook post-backup: {post_hook}")
                rc, out, err = ssh_exec(ssh2, post_hook, timeout=120)
                _log(state, f"  Hook: {'OK' if rc == 0 else 'ERREUR'} {(out + err).strip()[:200]}")
                ssh2.close()

            bkp_root  = os.path.join(data_dir, 'backups', subdir)
            existing  = sorted([d for d in os.listdir(bkp_root) if os.path.isdir(os.path.join(bkp_root, d))])
            max_count = int(backup.get('max_count', 7))
            for old in existing[:-max_count] if len(existing) > max_count else []:
                _log(state, f"Rotation (count) → suppression: {old}")
                shutil.rmtree(os.path.join(bkp_root, old), ignore_errors=True)

            max_days = int(backup.get('max_days', 0))
            if max_days > 0:
                cutoff = datetime.now() - timedelta(days=max_days)
                for d in sorted([d for d in os.listdir(bkp_root) if os.path.isdir(os.path.join(bkp_root, d))]):
                    full_d = os.path.join(bkp_root, d)
                    if datetime.fromtimestamp(os.path.getmtime(full_d)) < cutoff:
                        _log(state, f"Rotation (âge >{max_days}j) → suppression: {d}")
                        shutil.rmtree(full_d, ignore_errors=True)

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
                notify(webhook, {
                    'event': 'backup_success', 'timestamp': manifest['finished_at'],
                    'remote_name': remote.get('name', ''), 'host': remote.get('host', ''),
                    'backup_id': ts, 'size': human_size(total_size)
                })

        except Exception as e:
            state['last_status'] = 'error'
            manifest['status']   = 'error'
            manifest['error']    = str(e)
            _log(state, f"✗ Erreur: {e}")
            if ssh:
                try:
                    ssh.close()
                except Exception:
                    pass
            webhook = remote.get('backup', {}).get('webhook_url', '').strip()
            if webhook:
                notify(webhook, {'event': 'backup_error', 'error': str(e),
                                  'remote_name': remote.get('name', ''),
                                  'timestamp': datetime.now().isoformat()})
        finally:
            state['running'] = False

    threading.Thread(target=_run, daemon=True).start()
    return True, "Backup démarré"