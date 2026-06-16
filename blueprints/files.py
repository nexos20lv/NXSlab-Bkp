"""Routes explorateur de fichiers — /api/files/*"""
import os, shutil
from flask import Blueprint, request, jsonify, send_file
from blueprints.auth import login_required, admin_required
from core.config import get_data_dir
from core.helpers import human_size
from datetime import datetime

files_bp = Blueprint('files', __name__)


def _safe_path(rel):
    base = os.path.realpath(get_data_dir())
    full = os.path.realpath(os.path.join(base, rel.lstrip('/')))
    if full == base or full.startswith(base + os.sep):
        return full
    return None


@files_bp.route('/api/files/list')
@login_required
def files_list():
    rel  = request.args.get('path', '/')
    full = _safe_path(rel)
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
    rel_clean    = rel.strip('/')
    parent       = ('/' + '/'.join(rel_clean.split('/')[:-1])) if rel_clean else None
    rel_display  = os.path.relpath(full, base).replace('\\', '/')
    path_display = '/' if rel_display == '.' else '/' + rel_display
    return jsonify({'path': path_display, 'entries': entries, 'parent': parent})


@files_bp.route('/api/files/download')
@login_required
def files_download():
    rel  = request.args.get('path', '')
    full = _safe_path(rel)
    if not full or not os.path.isfile(full): return jsonify({'error': 'Fichier introuvable'}), 404
    return send_file(full, as_attachment=True)


@files_bp.route('/api/files/upload', methods=['POST'])
@admin_required  # NXS-SEC-002: mutating data under DATA_DIR is admin-only
def files_upload():
    rel  = request.args.get('path', '/')
    full = _safe_path(rel)
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


@files_bp.route('/api/files/mkdir', methods=['POST'])
@admin_required  # NXS-SEC-002: mutating data under DATA_DIR is admin-only
def files_mkdir():
    d      = request.json or {}
    parent = d.get('path', '/')
    name   = d.get('name', '').strip()
    if not name or '/' in name or name in ('..', '.'):
        return jsonify({'error': 'Nom invalide'}), 400
    full_p = _safe_path(parent)
    if not full_p or not os.path.isdir(full_p): return jsonify({'error': 'Répertoire parent invalide'}), 400
    try:
        os.makedirs(os.path.join(full_p, name), exist_ok=False)
        return jsonify({'ok': True})
    except FileExistsError: return jsonify({'error': 'Ce dossier existe déjà'}), 400
    except Exception as e:  return jsonify({'error': str(e)}), 500


@files_bp.route('/api/files/delete', methods=['POST'])
@admin_required  # NXS-SEC-002: mutating data under DATA_DIR is admin-only
def files_delete():
    rel  = (request.json or {}).get('path', '')
    full = _safe_path(rel)
    base = os.path.realpath(get_data_dir())
    if not full or full == base: return jsonify({'error': 'Impossible de supprimer la racine'}), 403
    if not os.path.exists(full): return jsonify({'error': 'Introuvable'}), 404
    try:
        shutil.rmtree(full) if os.path.isdir(full) else os.remove(full)
        return jsonify({'ok': True})
    except Exception as e: return jsonify({'error': str(e)}), 500


@files_bp.route('/api/files/rename', methods=['POST'])
@admin_required  # NXS-SEC-002: mutating data under DATA_DIR is admin-only
def files_rename():
    d        = request.json or {}
    rel      = d.get('path', '')
    new_name = d.get('name', '').strip()
    if not new_name or '/' in new_name or new_name in ('..', '.'):
        return jsonify({'error': 'Nom invalide'}), 400
    full = _safe_path(rel)
    if not full or not os.path.exists(full): return jsonify({'error': 'Introuvable'}), 404
    new_full = os.path.join(os.path.dirname(full), new_name)
    if os.path.exists(new_full): return jsonify({'error': 'Un élément avec ce nom existe déjà'}), 400
    try:
        os.rename(full, new_full)
        return jsonify({'ok': True})
    except Exception as e: return jsonify({'error': str(e)}), 500