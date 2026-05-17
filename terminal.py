"""WebSocket terminal SSH — enregistré via register_terminal(sock)"""
import json
import threading
from flask import session
from config import get_remote
from backup_core import ssh_connect


def register_terminal(sock):
    @sock.route('/ws/terminal/<remote_id>')
    def terminal_ws(ws, remote_id):
        if not session.get('logged_in'):
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

        ssh = None
        chan = None
        try:
            ssh  = ssh_connect(remote)
            chan = ssh.invoke_shell(term='xterm-256color', width=120, height=40)
            chan.settimeout(0.1)

            def read_remote():
                try:
                    while not chan.closed:
                        try:
                            data = chan.recv(4096)
                            if not data:
                                break
                            ws.send(data.decode('utf-8', errors='replace'))
                        except Exception:
                            break
                finally:
                    try:
                        ws.close()
                    except Exception:
                        pass

            threading.Thread(target=read_remote, daemon=True).start()

            while True:
                try:
                    msg = ws.receive()
                    if msg is None:
                        break
                    if isinstance(msg, str) and msg.startswith('{'):
                        try:
                            d = json.loads(msg)
                            if d.get('type') == 'resize':
                                chan.resize_pty(width=int(d.get('cols', 80)), height=int(d.get('rows', 24)))
                            continue
                        except Exception:
                            pass
                    chan.sendall(msg.encode('utf-8') if isinstance(msg, str) else msg)
                except Exception:
                    break
        except Exception as e:
            try:
                ws.send(f'\r\n\033[31m[Erreur: {e}]\033[0m\r\n')
                ws.close()
            except Exception:
                pass
        finally:
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
