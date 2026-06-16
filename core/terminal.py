"""WebSocket terminal SSH — enregistré via register_terminal(sock)"""
import json
import socket
import threading
from flask import session
from core.config import get_remote
from core.backup_core import ssh_connect

_TIMEOUT_EXC = (socket.timeout, TimeoutError)


def terminal_authorized(sess) -> bool:
    """NXS-SEC-003: the web SSH terminal grants an interactive shell on the
    remote VPS using stored credentials, so it must be admin-only — being merely
    authenticated (e.g. a readonly account) is not sufficient."""
    return bool(sess.get('logged_in')) and sess.get('role') == 'admin'


def register_terminal(sock):
    @sock.route('/ws/terminal/<remote_id>')
    def terminal_ws(ws, remote_id):
        if not terminal_authorized(session):
            try:
                ws.send('\r\n[Non autorisé]\r\n')
                ws.close()
            except Exception:
                pass
            return

        remote = get_remote(remote_id)
        if not remote:
            try:
                ws.send('\r\n[Remote introuvable]\r\n')
                ws.close()
            except Exception:
                pass
            return

        ssh  = None
        chan = None
        _closed = threading.Event()

        try:
            ssh  = ssh_connect(remote)
            chan = ssh.invoke_shell(term='xterm-256color', width=120, height=40)
            chan.settimeout(0.2)

            def read_remote():
                try:
                    while not _closed.is_set() and not chan.closed:
                        try:
                            data = chan.recv(4096)
                            if not data:
                                break
                            ws.send(data.decode('utf-8', errors='replace'))
                        except _TIMEOUT_EXC:
                            continue
                        except Exception:
                            break
                finally:
                    _closed.set()
                    try:
                        ws.close()
                    except Exception:
                        pass

            threading.Thread(target=read_remote, daemon=True).start()

            while not _closed.is_set():
                try:
                    msg = ws.receive()
                    if msg is None:
                        break
                    if isinstance(msg, str) and msg.startswith('{'):
                        try:
                            d = json.loads(msg)
                            if d.get('type') == 'resize':
                                chan.resize_pty(
                                    width=int(d.get('cols', 80)),
                                    height=int(d.get('rows', 24))
                                )
                            continue
                        except Exception:
                            pass
                    chan.sendall(msg.encode('utf-8') if isinstance(msg, str) else msg)
                except Exception:
                    break

        except Exception as e:
            try:
                ws.send(f'\r\n\033[31m[Erreur SSH: {e}]\033[0m\r\n')
                ws.close()
            except Exception:
                pass
        finally:
            _closed.set()
            if chan:
                try:
                    chan.close()
                except Exception:
                    pass
            if ssh:
                try:
                    ssh.close()
                except Exception:
                    pass