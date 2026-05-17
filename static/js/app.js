// ─── API helper ──────────────────────────────────────────────────────────
async function api(url, opts = {}) {
  const r = await fetch(url, {
    headers: {'Content-Type': 'application/json'},
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined
  });
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}

// ─── Toast ───────────────────────────────────────────────────────────────
function toast(msg, type = 'info') {
  const icons = {ok: 'fa-circle-check', err: 'fa-circle-xmark', info: 'fa-circle-info'};
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<i class="fa-solid ${icons[type]}"></i>${escHtml(msg)}`;
  document.getElementById('toasts').prepend(el);
  setTimeout(() => el.remove(), 3100);
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ─── Tabs ─────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    const t = btn.dataset.tab;
    if (t === 'samba')    { refreshSambaShares(); refreshSambaUsers(); refreshSambaConns(); }
    if (t === 'ftp')      { refreshFtpUsers(); refreshFtpConns(); }
    if (t === 'files')    { navigateTo(explorerPath); }
    if (t === 'logs')     { fetchLogs(); }
    if (t === 'backup')   { refreshRemoteCards(); }
    if (t === 'settings') { refreshUsers(); }
    if (t === 'terminal') { initTerminalTab(); }
  });
});

// ─── Status ───────────────────────────────────────────────────────────────
function setSvcBadge(id, state) {
  const el = document.getElementById(id);
  if (!el) return;
  el.dataset.s = state;
  const lbl = el.querySelector('.svc-lbl');
  const labels = {up:'actif', down:'arrêté', inactive:'inactif', failed:'erreur', checking:'—'};
  if (lbl) lbl.textContent = labels[state] || state;
}

async function refreshStatus() {
  document.getElementById('hero-refresh-ico').classList.add('spin');
  try {
    const d = await api('/api/status');
    document.getElementById('nav-hostname').textContent = d.hostname || '—';
    document.getElementById('hero-uptime').textContent  = d.uptime   || '—';
    document.getElementById('hero-ts').textContent      = d.ts       || '—';

    const up     = [d.samba, d.ftp].filter(s => s === 'up').length;
    const dot    = document.getElementById('hero-dot');
    const navDot = document.getElementById('nav-dot');
    dot.className    = 'hero-dot ' + (up === 2 ? 'up' : up > 0 ? 'degraded' : 'down');
    navDot.className = 'nav-dot '  + (up > 0   ? 'up' : 'down');
    document.getElementById('hero-text').textContent =
      up === 2 ? 'tous les services opérationnels'
      : up > 0 ? `service dégradé — ${up}/2 actifs`
      :          'services hors ligne';

    setSvcBadge('badge-samba',      d.samba);
    setSvcBadge('ctrl-badge-samba', d.samba);
    setSvcBadge('badge-ftp',        d.ftp);
    setSvcBadge('ctrl-badge-ftp',   d.ftp);
    const ddEl = document.getElementById('info-datadir');
    if (ddEl && d.data_dir) ddEl.textContent = d.data_dir;
  } catch(e) { toast('Erreur statut: ' + e.message, 'err'); }
  document.getElementById('hero-refresh-ico').classList.remove('spin');
}

async function refreshSystem() {
  try {
    const d = await api('/api/system');
    const cpu = parseFloat(d.cpu) || 0;
    document.getElementById('cpu-val').textContent  = cpu.toFixed(1) + '%';
    document.getElementById('load-val').textContent = `load: ${d.load['1m']} ${d.load['5m']} ${d.load['15m']}`;
    const cpuBar = document.getElementById('cpu-bar');
    cpuBar.style.width = Math.min(cpu, 100) + '%';
    cpuBar.className   = 'progress-fill' + (cpu > 90 ? ' crit' : cpu > 70 ? ' warn' : '');

    const m = d.memory;
    document.getElementById('mem-val').textContent  = m.used + ' MB';
    document.getElementById('mem-sub').textContent  = `${m.used} / ${m.total} MB`;
    document.getElementById('mem-pct').textContent  = m.percent + '%';
    document.getElementById('mem-free').textContent = m.free + ' MB libre';
    const memBar = document.getElementById('mem-bar');
    memBar.style.width = m.percent + '%';
    memBar.className   = 'progress-fill' + (m.percent > 90 ? ' crit' : m.percent > 75 ? ' warn' : '');

    const diskList = document.getElementById('disk-list');
    diskList.innerHTML = d.disks.length ? d.disks.map(disk => `
      <div>
        <div class="disk-info">
          <span class="disk-name">${escHtml(disk.mount)} <span style="color:var(--text-muted);font-size:.65rem;">(${escHtml(disk.device)})</span></span>
          <span class="disk-stats">${disk.used} / ${disk.size} — <span style="color:${disk.percent_int>90?'var(--down)':disk.percent_int>75?'var(--warn)':'var(--up)'}">${disk.percent}</span></span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill ${disk.percent_int>90?'crit':disk.percent_int>75?'warn':''}" style="width:${disk.percent_int}%"></div>
        </div>
      </div>`).join('') : '<span style="font-family:var(--font-mono);font-size:.72rem;color:var(--text-muted);">Aucune donnée</span>';
  } catch { /* silent */ }
}

document.getElementById('hero-refresh-ico').onclick = () => { refreshStatus(); refreshSystem(); };
setInterval(refreshStatus, 30000);
setInterval(refreshSystem, 30000);

// ─── Service control ──────────────────────────────────────────────────────
async function svcCtrl(svc, action) {
  const labels = {start:'Démarrage', stop:'Arrêt', restart:'Redémarrage', reload:'Rechargement'};
  try {
    const d = await api(svc === 'samba' ? '/api/samba/control' : '/api/ftp/control', {method:'POST', body:{action}});
    toast(labels[action] + (d.ok ? ' réussi' : ' échoué'), d.ok ? 'ok' : 'err');
    setTimeout(refreshStatus, 800);
  } catch(e) { toast(e.message, 'err'); }
}

// ─── Samba ────────────────────────────────────────────────────────────────
async function refreshSambaShares() {
  try {
    const d = await api('/api/samba/shares');
    const tbody = document.getElementById('shares-tbody');
    tbody.innerHTML = !d.shares?.length
      ? '<tr><td colspan="3" class="tbl-empty">Aucun partage configuré</td></tr>'
      : d.shares.map(s => `<tr>
          <td class="mono">${escHtml(s.name)}</td>
          <td class="mono">${escHtml(s.path || '—')}</td>
          <td><span style="color:${s['read only']==='yes'?'var(--warn)':'var(--up)'};">${s['read only']==='yes'?'oui':'non'}</span></td>
        </tr>`).join('');
  } catch(e) { toast('Erreur partages: ' + e.message, 'err'); }
}

async function refreshSambaUsers() {
  try {
    const d = await api('/api/samba/users');
    const tbody = document.getElementById('samba-users-tbody');
    tbody.innerHTML = !d.users?.length
      ? '<tr><td colspan="3" class="tbl-empty">Aucun utilisateur Samba</td></tr>'
      : d.users.map((u, i) => `<tr>
          <td class="mono">${escHtml(u.username)}</td>
          <td class="mono" style="color:var(--text-muted)">${escHtml(u.uid)}</td>
          <td><div style="display:flex;gap:4px;">
            <button class="btn-sm" onclick="openModal('samba-user-passwd','${escHtml(u.username)}')"><i class="fa-solid fa-key"></i></button>
            <button class="btn-sm danger" onclick="openModal('samba-user-del','${escHtml(u.username)}')"><i class="fa-solid fa-trash"></i></button>
          </div></td>
        </tr>`).join('');
  } catch(e) { toast('Erreur users Samba: ' + e.message, 'err'); }
}

async function refreshSambaConns() {
  try {
    const d = await api('/api/samba/connections');
    document.getElementById('samba-conns').textContent = d.output;
  } catch(e) { document.getElementById('samba-conns').textContent = 'Erreur: ' + e.message; }
}

async function loadSambaConfig() {
  try { document.getElementById('samba-cfg-ta').value = (await api('/api/samba/config')).content; }
  catch(e) { toast('Erreur config: ' + e.message, 'err'); }
}

async function saveSambaConfig() {
  try { await api('/api/samba/config', {method:'POST', body:{content: document.getElementById('samba-cfg-ta').value}}); toast('Configuration sauvegardée', 'ok'); }
  catch(e) { toast(e.message, 'err'); }
}

// ─── FTP ──────────────────────────────────────────────────────────────────
async function refreshFtpUsers() {
  try {
    const d = await api('/api/ftp/users');
    const tbody = document.getElementById('ftp-users-tbody');
    tbody.innerHTML = !d.users?.length
      ? '<tr><td colspan="5" class="tbl-empty">Aucun utilisateur (uid ≥ 1000)</td></tr>'
      : d.users.map(u => {
        const typeBadge = u.ftp_only
          ? `<span style="color:var(--accent);font-size:.62rem;border:1px solid rgba(0,200,255,.25);padding:1px 6px;border-radius:3px;">FTP</span>`
          : `<span style="color:var(--up);font-size:.62rem;border:1px solid rgba(34,211,108,.25);padding:1px 6px;border-radius:3px;">SHELL</span>`;
        const lockBadge = u.locked
          ? `<span style="color:var(--down);font-size:.62rem;margin-left:4px;"><i class="fa-solid fa-lock"></i></span>` : '';
        return `<tr>
          <td class="mono">${escHtml(u.username)}</td>
          <td class="mono" style="color:var(--text-muted);font-size:.68rem;">${escHtml(u.home)}</td>
          <td>${typeBadge}${lockBadge}</td>
          <td><span style="font-family:var(--font-mono);font-size:.62rem;color:${u.locked?'var(--down)':'var(--up)'};">${u.locked?'Verrouillé':'Actif'}</span></td>
          <td><div style="display:flex;gap:3px;flex-wrap:wrap;">
            <button class="btn-sm" title="Mot de passe" onclick="openModal('ftp-user-passwd','${escHtml(u.username)}')"><i class="fa-solid fa-key"></i></button>
            <button class="btn-sm" title="${u.ftp_only?'Activer shell':'FTP seulement'}" onclick="toggleFtpShell('${escHtml(u.username)}',${!u.ftp_only})">
              <i class="fa-solid ${u.ftp_only?'fa-terminal':'fa-ban'}"></i>
            </button>
            <button class="btn-sm" title="${u.locked?'Déverrouiller':'Verrouiller'}" onclick="toggleFtpLock('${escHtml(u.username)}',${!u.locked})">
              <i class="fa-solid ${u.locked?'fa-lock-open':'fa-lock'}"></i>
            </button>
            <button class="btn-sm danger" title="Supprimer" onclick="openModal('ftp-user-del','${escHtml(u.username)}')"><i class="fa-solid fa-trash"></i></button>
          </div></td>
        </tr>`;
      }).join('');
  } catch(e) { toast('Erreur users FTP: ' + e.message, 'err'); }
}

async function toggleFtpShell(username, ftpOnly) {
  try {
    await api('/api/ftp/users/shell', {method:'POST', body:{username, ftp_only: ftpOnly}});
    toast(`${username}: shell ${ftpOnly ? 'FTP seulement' : 'bash activé'}`, 'ok');
    refreshFtpUsers();
  } catch(e) { toast(e.message, 'err'); }
}

async function toggleFtpLock(username, lock) {
  try {
    await api('/api/ftp/users/lock', {method:'POST', body:{username, lock}});
    toast(`${username} ${lock ? 'verrouillé' : 'déverrouillé'}`, 'ok');
    refreshFtpUsers();
  } catch(e) { toast(e.message, 'err'); }
}

async function refreshFtpConns() {
  try {
    const d = await api('/api/ftp/connections');
    document.getElementById('ftp-conns-box').textContent = d.connections || '(aucune)';
    document.getElementById('ftp-log-box').textContent   = d.log || '(aucun journal)';
    const el = document.getElementById('ftp-conn-count');
    if (el) el.textContent = d.count || '0';
  } catch(e) { toast('Erreur connexions FTP: ' + e.message, 'err'); }
}

async function loadFtpConfig() {
  try { document.getElementById('ftp-cfg-ta').value = (await api('/api/ftp/config')).content; }
  catch(e) { toast('Erreur config: ' + e.message, 'err'); }
}

async function saveFtpConfig() {
  try {
    await api('/api/ftp/config', {method:'POST', body:{content: document.getElementById('ftp-cfg-ta').value}});
    toast('Configuration sauvegardée', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

function toggleConfig(svc) {
  const toggle = document.getElementById(svc + '-cfg-toggle');
  const body   = document.getElementById(svc + '-cfg-body');
  toggle.classList.toggle('open');
  body.classList.toggle('open');
  if (body.classList.contains('open')) {
    if (svc === 'samba') loadSambaConfig();
    if (svc === 'ftp')   loadFtpConfig();
  }
}

// ─── File Explorer ────────────────────────────────────────────────────────
let explorerPath = '/';
let _files = [];

const FILE_ICONS = {
  dir:  {i: 'fa-folder',         c: 'var(--warn)'},
  gz:   {i: 'fa-file-zipper',    c: 'var(--accent)'},
  zip:  {i: 'fa-file-zipper',    c: 'var(--accent)'},
  tar:  {i: 'fa-file-zipper',    c: 'var(--accent)'},
  bz2:  {i: 'fa-file-zipper',    c: 'var(--accent)'},
  xz:   {i: 'fa-file-zipper',    c: 'var(--accent)'},
  '7z': {i: 'fa-file-zipper',    c: 'var(--accent)'},
  rar:  {i: 'fa-file-zipper',    c: 'var(--accent)'},
  jpg:  {i: 'fa-file-image',     c: '#e96c8c'},
  jpeg: {i: 'fa-file-image',     c: '#e96c8c'},
  png:  {i: 'fa-file-image',     c: '#e96c8c'},
  gif:  {i: 'fa-file-image',     c: '#e96c8c'},
  mp4:  {i: 'fa-file-video',     c: '#a78bfa'},
  mkv:  {i: 'fa-file-video',     c: '#a78bfa'},
  avi:  {i: 'fa-file-video',     c: '#a78bfa'},
  mp3:  {i: 'fa-file-audio',     c: '#f472b6'},
  flac: {i: 'fa-file-audio',     c: '#f472b6'},
  pdf:  {i: 'fa-file-pdf',       c: '#f87171'},
  sh:   {i: 'fa-file-code',      c: 'var(--up)'},
  py:   {i: 'fa-file-code',      c: 'var(--up)'},
  js:   {i: 'fa-file-code',      c: 'var(--up)'},
  ts:   {i: 'fa-file-code',      c: 'var(--up)'},
  json: {i: 'fa-file-code',      c: 'var(--up)'},
  yaml: {i: 'fa-file-code',      c: 'var(--up)'},
  yml:  {i: 'fa-file-code',      c: 'var(--up)'},
  conf: {i: 'fa-file-code',      c: 'var(--up)'},
  sql:  {i: 'fa-database',       c: '#60a5fa'},
  txt:  {i: 'fa-file-lines',     c: 'var(--text-muted)'},
  log:  {i: 'fa-file-lines',     c: 'var(--text-muted)'},
  csv:  {i: 'fa-file-csv',       c: 'var(--up)'},
  _def: {i: 'fa-file',           c: 'var(--text-muted)'}
};

function fileIcon(entry) {
  if (entry.type === 'dir') return FILE_ICONS.dir;
  const ext = entry.name.includes('.') ? entry.name.split('.').pop().toLowerCase() : '';
  return FILE_ICONS[ext] || FILE_ICONS._def;
}

async function navigateTo(path) {
  explorerPath = path;
  const ico = document.getElementById('explorer-refresh-ico');
  if (ico) ico.classList.add('spin');
  const tbody = document.getElementById('files-tbody');
  tbody.innerHTML = '<tr><td colspan="5" class="tbl-empty"><i class="fa-solid fa-rotate spin" style="margin-right:6px;"></i>Chargement...</td></tr>';
  try {
    const d = await api('/api/files/list?path=' + encodeURIComponent(path));
    explorerPath = d.path;
    renderBreadcrumb(d.path);
    renderFiles(d.entries, d.parent);
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="5" class="tbl-empty" style="color:var(--down)">Erreur: ${escHtml(e.message)}</td></tr>`;
  }
  if (ico) ico.classList.remove('spin');
}

function renderBreadcrumb(path) {
  const bc    = document.getElementById('breadcrumb');
  const parts = path.split('/').filter(Boolean);
  let html = `<span class="bc-root" onclick="navigateTo('/')"><i class="fa-solid fa-hard-drive"></i>&nbsp;bkp-data</span>`;
  parts.forEach((part, i) => {
    const navPath = '/' + parts.slice(0, i + 1).join('/');
    html += `<span class="bc-sep">/</span>`;
    if (i === parts.length - 1) {
      html += `<span class="bc-part active">${escHtml(part)}</span>`;
    } else {
      html += `<span class="bc-part" onclick="navigateTo('${escHtml(navPath)}')">${escHtml(part)}</span>`;
    }
  });
  bc.innerHTML = html;
}

function renderFiles(entries, parent) {
  _files = entries;
  const tbody = document.getElementById('files-tbody');
  let html = '';

  if (parent !== null && parent !== undefined) {
    html += `<tr onclick="navigateTo('${escHtml(parent)}')" style="cursor:pointer;">
      <td><i class="fa-solid fa-turn-up" style="color:var(--text-muted);font-size:.75rem;"></i></td>
      <td class="mono" style="color:var(--text-muted);">..</td>
      <td>—</td><td>—</td><td></td>
    </tr>`;
  }

  if (!entries.length && html === '') {
    tbody.innerHTML = '<tr><td colspan="5" class="tbl-empty"><i class="fa-solid fa-folder-open" style="margin-right:6px;opacity:.4;"></i>Dossier vide</td></tr>';
    return;
  }

  entries.forEach((e, i) => {
    const ic = fileIcon(e);
    const nameCell = e.type === 'dir'
      ? `<span class="file-name-dir" onclick="navigateTo('${escHtml(e.path)}')">${escHtml(e.name)}<span class="file-slash">/</span></span>`
      : `<span class="file-name-file">${escHtml(e.name)}</span>`;

    const actions = e.type === 'file'
      ? `<a class="btn-sm" href="/api/files/download?path=${encodeURIComponent(e.path)}" title="Télécharger" style="text-decoration:none;"><i class="fa-solid fa-download"></i></a>
         <button class="btn-sm" onclick="openModal('files-rename',${i})"><i class="fa-solid fa-pencil"></i></button>
         <button class="btn-sm danger" onclick="openModal('files-delete',${i})"><i class="fa-solid fa-trash"></i></button>`
      : `<button class="btn-sm" onclick="openModal('files-rename',${i})"><i class="fa-solid fa-pencil"></i></button>
         <button class="btn-sm danger" onclick="openModal('files-delete',${i})"><i class="fa-solid fa-trash"></i></button>`;

    html += `<tr>
      <td class="file-icon"><i class="fa-solid ${ic.i}" style="color:${ic.c};"></i></td>
      <td class="mono">${nameCell}</td>
      <td style="color:var(--text-muted);font-family:var(--font-mono);font-size:.68rem;">${escHtml(e.size_h)}</td>
      <td style="color:var(--text-muted);font-family:var(--font-mono);font-size:.68rem;">${escHtml(e.mtime)}</td>
      <td><div style="display:flex;gap:3px;">${actions}</div></td>
    </tr>`;
  });

  tbody.innerHTML = html || '<tr><td colspan="5" class="tbl-empty">Dossier vide</td></tr>';
}

// Upload via XHR (for progress)
function uploadFiles(files) {
  if (!files.length) return;
  const prog     = document.getElementById('upload-prog');
  const progText = document.getElementById('upload-prog-text');
  const progBar  = document.getElementById('upload-prog-bar');
  prog.style.display = 'flex';

  const fd = new FormData();
  Array.from(files).forEach(f => fd.append('files', f));

  const xhr = new XMLHttpRequest();
  xhr.upload.onprogress = e => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      progBar.style.width = pct + '%';
      progText.textContent = `Téléversement… ${pct}%`;
    }
  };
  xhr.onload = () => {
    prog.style.display = 'none';
    progBar.style.width = '0%';
    document.getElementById('file-input').value = '';
    try {
      const d = JSON.parse(xhr.responseText);
      if (d.ok) { toast(`${d.saved.length} fichier(s) téléversé(s)`, 'ok'); navigateTo(explorerPath); }
      else toast(d.error || 'Erreur upload', 'err');
    } catch { toast('Erreur upload', 'err'); }
  };
  xhr.onerror = () => { prog.style.display = 'none'; toast('Erreur réseau', 'err'); };
  xhr.open('POST', '/api/files/upload?path=' + encodeURIComponent(explorerPath));
  xhr.send(fd);
}

// Drag & drop
const dropZone = document.getElementById('drop-zone');
document.addEventListener('dragover', e => e.preventDefault());
document.addEventListener('drop', e => {
  e.preventDefault();
  if (!document.getElementById('tab-files').classList.contains('active')) return;
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
});
dropZone.addEventListener('dragenter', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', ()  => dropZone.classList.remove('drag-over'));

// ─── Logs ─────────────────────────────────────────────────────────────────
let logSvc = 'samba';
let logArId = null;

function setLogSvc(svc, btn) {
  logSvc = svc;
  document.querySelectorAll('#log-svc-group .btn-sm').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  fetchLogs();
}

function toggleLogAR() {
  const ico = document.getElementById('log-ar-ico');
  if (logArId) {
    clearInterval(logArId); logArId = null;
    ico.className = 'fa-solid fa-pause';
    toast('Auto-refresh désactivé', 'info');
  } else {
    logArId = setInterval(fetchLogs, 5000);
    ico.className = 'fa-solid fa-play';
    toast('Auto-refresh activé (5s)', 'info');
  }
}

async function fetchLogs() {
  const lines = document.getElementById('log-lines').value;
  const ico   = document.getElementById('log-refresh-ico');
  ico.classList.add('spin');
  try {
    const d   = await api(`/api/logs/${logSvc}?lines=${lines}`);
    const box = document.getElementById('log-box');
    box.innerHTML = (d.logs || '').split('\n').map(line => {
      const cl = /error|fail|crit/i.test(line)      ? 'log-err'
               : /warn/i.test(line)                   ? 'log-warn'
               : /info|started|success/i.test(line)   ? 'log-info'
               : '';
      return cl ? `<span class="${cl}">${escHtml(line)}</span>` : escHtml(line);
    }).join('\n');
    box.scrollTop = box.scrollHeight;
  } catch(e) { document.getElementById('log-box').textContent = 'Erreur: ' + e.message; }
  ico.classList.remove('spin');
}

// ─── Change password ──────────────────────────────────────────────────────
async function changePassword() {
  const cur  = document.getElementById('pw-current').value;
  const nw   = document.getElementById('pw-new').value;
  const conf = document.getElementById('pw-confirm').value;
  if (nw !== conf) { toast('Les mots de passe ne correspondent pas', 'err'); return; }
  const btn = document.getElementById('pw-btn');
  const ico = document.getElementById('pw-ico');
  btn.disabled = true; ico.className = 'fa-solid fa-rotate spin';
  try {
    await api('/api/settings/password', {method:'POST', body:{current:cur, new:nw}});
    toast('Mot de passe modifié', 'ok');
    ['pw-current','pw-new','pw-confirm'].forEach(id => document.getElementById(id).value = '');
  } catch(e) { toast(e.message, 'err'); }
  btn.disabled = false; ico.className = 'fa-solid fa-key';
}

// ─── Modal ────────────────────────────────────────────────────────────────
let _modalAction = null;

function openModal(type, arg) {
  const title   = document.getElementById('modal-title');
  const sub     = document.getElementById('modal-sub');
  const fields  = document.getElementById('modal-fields');
  const confirm = document.getElementById('modal-confirm');

  const fld = (label, id, placeholder, type = 'text') =>
    `<div class="form-field"><label>${label}</label><input type="${type}" id="${id}" placeholder="${placeholder}" /></div>`;
  const chk = (label, id, checked = true, hint = '') =>
    `<div class="form-field" style="display:flex;align-items:center;gap:10px;padding:6px 0"><input type="checkbox" id="${id}"${checked?' checked':''} style="width:16px;height:16px;accent-color:var(--accent);cursor:pointer"/><span style="font-size:.82rem;color:var(--text)">${label}${hint?`<span style="color:var(--text-muted);font-size:.75rem;display:block">${hint}</span>`:''}</span></div>`;
  const v = id => { const el = document.getElementById(id); return el ? el.value : ''; };
  const vc = id => { const el = document.getElementById(id); return el ? el.checked : false; };

  const cfgs = {
    'samba-user-add': {
      title: 'Ajouter un utilisateur Samba',
      sub: "Crée un utilisateur système (si inexistant) et l'ajoute à Samba.",
      fields: fld("Nom d'utilisateur","m-user","exemple") + fld("Mot de passe","m-pass","min. 6 car.","password"),
      confirm: 'Ajouter', danger: false,
      action: async () => { await api('/api/samba/users/add',{method:'POST',body:{username:v('m-user'),password:v('m-pass')}}); refreshSambaUsers(); toast('Utilisateur ajouté','ok'); }
    },
    'samba-user-passwd': {
      title: `Mot de passe — ${arg}`,
      sub: 'Nouveau mot de passe Samba.',
      fields: fld("Nouveau mot de passe","m-pass","min. 6 car.","password"),
      confirm: 'Changer',
      action: async () => { await api('/api/samba/users/passwd',{method:'POST',body:{username:arg,password:v('m-pass')}}); toast('Mot de passe modifié','ok'); }
    },
    'samba-user-del': {
      title: `Supprimer ${arg}`,
      sub: `Supprimer l'utilisateur Samba "${arg}" ?`,
      fields: '', confirm: 'Supprimer', danger: true,
      action: async () => { await api('/api/samba/users/delete',{method:'POST',body:{username:arg}}); refreshSambaUsers(); toast('Supprimé','ok'); }
    },
    'ftp-user-add': {
      title: 'Ajouter un utilisateur FTP',
      sub: 'Crée un utilisateur système avec répertoire home.',
      fields: fld("Nom d'utilisateur","m-user","exemple") + fld("Mot de passe","m-pass","min. 6 car.","password") + fld("Home (optionnel)","m-home","/home/exemple") + chk("FTP uniquement (pas de shell SSH)","m-ftp-only",true,"L'utilisateur ne pourra pas se connecter en SSH ni en console"),
      confirm: 'Créer',
      action: async () => { await api('/api/ftp/users/add',{method:'POST',body:{username:v('m-user'),password:v('m-pass'),home:v('m-home'),ftp_only:vc('m-ftp-only')}}); refreshFtpUsers(); toast('Utilisateur créé','ok'); }
    },
    'ftp-user-passwd': {
      title: `Mot de passe — ${arg}`,
      sub: 'Nouveau mot de passe système.',
      fields: fld("Nouveau mot de passe","m-pass","min. 6 car.","password"),
      confirm: 'Changer',
      action: async () => { await api('/api/ftp/users/passwd',{method:'POST',body:{username:arg,password:v('m-pass')}}); toast('Mot de passe modifié','ok'); }
    },
    'ftp-user-del': {
      title: `Supprimer ${arg}`,
      sub: `Supprimer l'utilisateur "${arg}" et son home ?`,
      fields: '', confirm: 'Supprimer', danger: true,
      action: async () => { await api('/api/ftp/users/delete',{method:'POST',body:{username:arg}}); refreshFtpUsers(); toast('Supprimé','ok'); }
    },
    'files-mkdir': {
      title: 'Nouveau dossier',
      sub: `Créer un dossier dans : ${explorerPath}`,
      fields: fld("Nom du dossier","m-name","mon-dossier"),
      confirm: 'Créer',
      action: async () => { await api('/api/files/mkdir',{method:'POST',body:{path:explorerPath,name:v('m-name')}}); navigateTo(explorerPath); toast('Dossier créé','ok'); }
    },
    'files-rename': {
      title: `Renommer — ${_files[arg]?.name}`,
      sub: 'Choisissez un nouveau nom.',
      fields: fld("Nouveau nom","m-name",_files[arg]?.name || ''),
      confirm: 'Renommer',
      action: async () => { await api('/api/files/rename',{method:'POST',body:{path:_files[arg].path,name:v('m-name')}}); navigateTo(explorerPath); toast('Renommé','ok'); }
    },
    'files-delete': {
      title: `Supprimer ${_files[arg]?.name}`,
      sub: _files[arg]?.type === 'dir'
        ? `Supprimer le dossier "${_files[arg]?.name}" et tout son contenu ? Irréversible.`
        : `Supprimer le fichier "${_files[arg]?.name}" ? Irréversible.`,
      fields: '', confirm: 'Supprimer', danger: true,
      action: async () => { await api('/api/files/delete',{method:'POST',body:{path:_files[arg].path}}); navigateTo(explorerPath); toast('Supprimé','ok'); }
    },
    'remote-add': {
      title: 'Ajouter un VPS distant',
      sub: 'Le remote sera créé avec une configuration par défaut, modifiable ensuite.',
      fields: fld("Nom affiché","m-rname","Mon VPS") + fld("Hôte / IP","m-rhost","1.2.3.4 ou vps.domain.tld") +
              `<div style="display:flex;gap:8px;">${fld("Port SSH","m-rport","22")}${fld("Utilisateur","m-ruser","root")}</div>` +
              `<div class="form-field"><label>Authentification</label><select id="m-rauth" style="width:100%;background:rgba(0,0,0,.3);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);font-family:var(--font-mono);font-size:.82rem;"><option value="key">Clé SSH</option><option value="password">Mot de passe</option></select></div>` +
              fld("Chemin clé privée","m-rkeypath","/root/.ssh/id_rsa"),
      confirm: 'Ajouter',
      action: async () => {
        await api('/api/remotes/add', {method:'POST', body:{
          name: v('m-rname'), host: v('m-rhost'),
          port: parseInt(v('m-rport'))||22, user: v('m-ruser')||'root',
          auth_type: document.getElementById('m-rauth')?.value||'key',
          key_path: v('m-rkeypath')||'/root/.ssh/id_rsa',
        }});
        toast('VPS ajouté', 'ok'); refreshRemoteCards();
      }
    },
    'remote-edit': {
      title: `Éditer — ${_editRemoteData.name || arg || ''}`,
      sub: 'Modifier les informations de connexion SSH.',
      fields: fld("Nom affiché","m-rname", _editRemoteData.name||'') +
              fld("Hôte / IP","m-rhost", _editRemoteData.host||'') +
              `<div style="display:flex;gap:8px;">${fld("Port SSH","m-rport", String(_editRemoteData.port||22))}${fld("Utilisateur","m-ruser", _editRemoteData.user||'root')}</div>` +
              fld("Chemin clé privée","m-rkeypath", _editRemoteData.key_path||'/root/.ssh/id_rsa'),
      confirm: 'Sauvegarder',
      action: async () => {
        const rid = _editRemoteData.id || arg;
        await api('/api/remotes/update', {method:'POST', body:{
          id: rid, name: v('m-rname'), host: v('m-rhost'),
          port: parseInt(v('m-rport'))||22, user: v('m-ruser')||'root',
          key_path: v('m-rkeypath'),
        }});
        toast('Remote mis à jour', 'ok'); refreshRemoteCards();
      }
    },
    'user-add': {
      title: 'Ajouter un utilisateur WebUI',
      sub: "Accès à l'interface de gestion NXSlab.",
      fields: fld("Nom d'utilisateur","m-user","exemple") + fld("Mot de passe","m-pass","min. 8 car.","password") +
              `<div class="form-field"><label>Rôle</label><select id="m-role" style="width:100%;background:rgba(0,0,0,.3);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);font-family:var(--font-mono);font-size:.82rem;"><option value="readonly">readonly — consultation seule</option><option value="admin">admin — accès complet</option></select></div>`,
      confirm: 'Créer',
      action: async () => {
        await api('/api/users/add', {method:'POST', body:{username:v('m-user'), password:v('m-pass'), role: document.getElementById('m-role')?.value||'readonly'}});
        refreshUsers(); toast('Utilisateur créé', 'ok');
      }
    },
    'user-del': {
      title: `Supprimer ${arg}`,
      sub: `Supprimer le compte "${arg}" ? L'utilisateur ne pourra plus se connecter.`,
      fields: '', confirm: 'Supprimer', danger: true,
      action: async () => { await api('/api/users/delete',{method:'POST',body:{username:arg}}); refreshUsers(); toast('Utilisateur supprimé','ok'); }
    },
    'user-role': (() => {
      const [uname, currentRole] = (arg||'').split('|');
      return {
        title: `Rôle — ${uname}`,
        sub: `Modifier le rôle de "${uname}".`,
        fields: `<div class="form-field"><label>Rôle</label><select id="m-role" style="width:100%;background:rgba(0,0,0,.3);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);font-family:var(--font-mono);font-size:.82rem;"><option value="readonly"${currentRole==='readonly'?' selected':''}>readonly — consultation seule</option><option value="admin"${currentRole==='admin'?' selected':''}>admin — accès complet</option></select></div>`,
        confirm: 'Modifier',
        action: async () => { await api('/api/users/role',{method:'POST',body:{username:uname,role:document.getElementById('m-role')?.value||'readonly'}}); refreshUsers(); toast('Rôle modifié','ok'); }
      };
    })(),
  };

  const cfg = cfgs[type];
  if (!cfg) return;
  title.textContent   = cfg.title;
  sub.textContent     = cfg.sub;
  fields.innerHTML    = cfg.fields;
  confirm.textContent = cfg.confirm;
  confirm.className   = 'btn-confirm' + (cfg.danger ? ' danger' : '');
  _modalAction = cfg.action;
  document.getElementById('modal-overlay').classList.add('open');
  const first = fields.querySelector('input');
  if (first) setTimeout(() => first.focus(), 80);
}

async function modalConfirm() {
  const btn = document.getElementById('modal-confirm');
  btn.disabled = true;
  try { await _modalAction(); closeModal(); }
  catch(e) { toast(e.message, 'err'); }
  btn.disabled = false;
}

function closeModal(e) {
  if (e && e.target !== document.getElementById('modal-overlay')) return;
  document.getElementById('modal-overlay').classList.remove('open');
  document.getElementById('modal-confirm').style.display = '';
  _modalAction = null;
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ─── Backup summary (dashboard) ──────────────────────────────────────────
async function refreshBackupSummary() {
  try {
    const data    = await api('/api/remotes');
    const remotes = data.remotes || [];
    const section = document.getElementById('bkp-summary-section');
    const grid    = document.getElementById('bkp-summary-grid');
    if (!remotes.length) { section.style.display = 'none'; return; }
    section.style.display = '';
    grid.innerHTML = remotes.map(r => {
      const stColor  = r.last_status === 'ok' ? 'var(--up)' : r.last_status === 'error' ? 'var(--down)' : 'var(--text-muted)';
      const stLabel  = r.last_status === 'ok' ? 'OK' : r.last_status === 'error' ? 'Erreur' : r.running ? 'En cours…' : 'Jamais';
      const lastRun  = r.last_run ? r.last_run.replace('T',' ').slice(0,16) : '—';
      const nextLine = r.schedule_enabled && r.next_run
        ? `<div class="bkp-sum-next"><i class="fa-regular fa-clock"></i> Prochain: ${escHtml(r.next_run)}</div>`
        : `<div class="bkp-sum-next"><i class="fa-regular fa-clock"></i> Planification désactivée</div>`;
      return `<div class="bkp-sum-card" onclick="document.querySelector('[data-tab=backup]').click();setTimeout(()=>selectRemote('${r.id}'),120);">
        <div class="bkp-sum-top">
          <span style="width:8px;height:8px;border-radius:50%;background:${stColor};flex-shrink:0;${r.last_status?`box-shadow:0 0 5px ${stColor}`:''}"></span>
          <span class="bkp-sum-name">${escHtml(r.name)}</span>
          ${r.running ? '<span style="font-family:var(--font-mono);font-size:.58rem;color:var(--accent);">● actif</span>' : ''}
        </div>
        <div class="bkp-sum-row"><span>Hôte</span><span>${escHtml(r.host)}</span></div>
        <div class="bkp-sum-row"><span>Dernier backup</span><span>${escHtml(lastRun)}</span></div>
        <div class="bkp-sum-row"><span>État</span><span style="color:${stColor}">${stLabel}</span></div>
        ${nextLine}
      </div>`;
    }).join('');
  } catch { /* silent */ }
}

// ─── Remote stats (dashboard) ─────────────────────────────────────────────
async function refreshAllRemoteStats() {
  try {
    const remotes = await api('/api/remotes');
    const grid    = document.getElementById('remote-stats-grid');
    const section = document.getElementById('remote-stats-section');
    if (!remotes.remotes?.length) { section.style.display = 'none'; return; }
    section.style.display = '';
    for (const r of remotes.remotes) {
      let card = document.getElementById('rst-' + r.id);
      if (!card) {
        card = document.createElement('div');
        card.className = 'remote-stat-card'; card.id = 'rst-' + r.id;
        grid.appendChild(card);
      }
      card.innerHTML = `<div class="remote-stat-title"><span class="stat-dot" style="background:var(--text-muted)"></span>${escHtml(r.name)} <span style="color:var(--text-muted);font-size:.62rem;">${escHtml(r.host)}</span></div>
        <div style="font-family:var(--font-mono);font-size:.68rem;color:var(--text-muted);">Connexion...</div>`;
      (async () => {
        try {
          const s = await api(`/api/remote/${r.id}/stats`);
          if (!s.ok) { card.querySelector('div:last-child').textContent = '✗ ' + (s.error||'Erreur'); return; }
          const dotColor = 'var(--up)';
          card.innerHTML = `
            <div class="remote-stat-title"><span class="stat-dot" style="background:${dotColor};box-shadow:0 0 5px ${dotColor}"></span>${escHtml(r.name)} <span style="color:var(--text-muted);font-size:.62rem;">${escHtml(r.host)}</span></div>
            <div class="remote-stat-row"><span>CPU</span><span>${parseFloat(s.cpu||0).toFixed(1)}%</span></div>
            <div class="remote-stat-row"><span>Mémoire</span><span>${s.memory?.used||0} / ${s.memory?.total||0} MB (${s.memory?.percent||0}%)</span></div>
            <div class="remote-stat-row"><span>Load</span><span>${s.load?.['1m']||0} ${s.load?.['5m']||0} ${s.load?.['15m']||0}</span></div>
            <div class="remote-stat-row"><span>Uptime</span><span>${escHtml(s.uptime||'—')}</span></div>
            ${s.disks?.length ? `<div class="remote-stat-row"><span>Disque /</span><span>${escHtml((s.disks.find(d=>d.mount==='/')||s.disks[0])?.percent||'?')}</span></div>` : ''}
            ${s.containers?.length ? `<div class="remote-stat-containers">${s.containers.map(c=>`<span class="container-badge"><i class="fa-brands fa-docker" style="color:var(--accent);font-size:.55rem;"></i> ${escHtml(c.name)}</span>`).join('')}</div>` : ''}`;
        } catch(e) {
          const last = card.querySelector('div:last-child');
          if (last) last.textContent = '✗ ' + e.message;
        }
      })();
    }
  } catch { /* silent */ }
}

// ─── Multi-remote management ──────────────────────────────────────────────
let _selectedRemoteId = null;
let _bkpPollId        = null;
let _bkpChart         = null;

async function refreshRemoteCards() {
  try {
    const data = await api('/api/remotes');
    const remotes   = data.remotes || [];
    const container = document.getElementById('remote-cards');
    const detail    = document.getElementById('bkp-remote-detail');
    const noRemote  = document.getElementById('bkp-no-remote');

    container.innerHTML = remotes.map(r => {
      const status  = r.last_status === 'ok' ? 'var(--up)' : r.last_status === 'error' ? 'var(--down)' : 'var(--text-muted)';
      const lastRun = r.last_run ? r.last_run.replace('T',' ').slice(0,16) : 'jamais';
      const isActive = r.id === _selectedRemoteId;
      const nextLine = r.schedule_enabled && r.next_run
        ? `<span class="remote-card-meta" style="color:var(--accent);opacity:.8;"><i class="fa-regular fa-clock" style="font-size:.58rem;"></i> ${escHtml(r.next_run)}</span>`
        : '';
      return `<div class="remote-card${isActive?' active':''}" id="rc-${r.id}" onclick="selectRemote('${r.id}')">
        <div class="remote-card-top">
          <span class="remote-card-name">${escHtml(r.name)}</span>
          ${r.running ? '<span style="font-family:var(--font-mono);font-size:.60rem;color:var(--accent);">● en cours</span>'
            : `<span style="width:7px;height:7px;border-radius:50%;background:${status};display:inline-block;flex-shrink:0;"></span>`}
        </div>
        <span class="remote-card-host"><i class="fa-solid fa-server" style="font-size:.60rem;"></i> ${escHtml(r.host)}</span>
        <span class="remote-card-meta">Dernier backup: ${escHtml(lastRun)}</span>
        ${nextLine}
        <div class="remote-card-actions" onclick="event.stopPropagation()">
          <button class="remote-card-btn" onclick="openEditRemote('${r.id}')"><i class="fa-solid fa-pen"></i> Éditer</button>
          <button class="remote-card-btn danger" onclick="deleteRemote('${r.id}','${escHtml(r.name)}')"><i class="fa-solid fa-trash"></i></button>
        </div>
      </div>`;
    }).join('');

    if (remotes.length === 0) {
      noRemote.style.display = ''; detail.style.display = 'none';
    } else {
      noRemote.style.display = 'none';
      if (!_selectedRemoteId || !remotes.find(r => r.id === _selectedRemoteId)) {
        selectRemote(remotes[0].id);
      } else {
        detail.style.display = '';
      }
    }
    const termSel = document.getElementById('term-remote-sel');
    if (termSel) {
      termSel.innerHTML = '<option value="">— sélectionner un VPS —</option>' +
        remotes.map(r => `<option value="${r.id}"${r.id===_selectedRemoteId?' selected':''}>${escHtml(r.name)} (${escHtml(r.host)})</option>`).join('');
    }
  } catch(e) { toast('Erreur remotes: ' + e.message, 'err'); }
}

function selectRemote(id) {
  _selectedRemoteId = id;
  stopBkpPoll();
  document.querySelectorAll('.remote-card').forEach(c => c.classList.remove('active'));
  const card = document.getElementById('rc-' + id);
  if (card) card.classList.add('active');
  document.getElementById('bkp-remote-detail').style.display = '';
  loadBackupSettings();
  refreshBackupList();
  refreshBackupStatus();
}

async function deleteRemote(id, name) {
  if (!confirm(`Supprimer le remote "${name}" ? La configuration sera perdue (les backups existants restent).`)) return;
  try {
    await api('/api/remotes/delete', {method:'POST', body:{id}});
    if (_selectedRemoteId === id) { _selectedRemoteId = null; stopBkpPoll(); }
    toast('Remote supprimé', 'ok');
    refreshRemoteCards();
  } catch(e) { toast(e.message, 'err'); }
}

function openEditRemote(id) { openModal('remote-edit', id); }

// ─── Backup ───────────────────────────────────────────────────────────────

function toggleAuthFields() {
  const auth = document.getElementById('r-auth').value;
  document.getElementById('r-key-fields').style.display = auth === 'key' ? '' : 'none';
  document.getElementById('r-pw-fields').style.display  = auth === 'password' ? '' : 'none';
}

function setCron(expr) { document.getElementById('b-schedule').value = expr; }

function addPathItem(listId, placeholder, value = '') {
  const item = document.createElement('div');
  item.className = 'bkp-path-item';
  item.innerHTML = `<input type="text" placeholder="${escHtml(placeholder)}" value="${escHtml(value)}" />
    <button class="bkp-path-del" onclick="this.parentElement.remove()"><i class="fa-solid fa-xmark"></i></button>`;
  document.getElementById(listId).appendChild(item);
  item.querySelector('input').focus();
}

function getPathList(listId) {
  return Array.from(document.querySelectorAll(`#${listId} .bkp-path-item input[type="text"]`))
    .map(i => i.value.trim()).filter(Boolean);
}

function addDbEntry(type, data = {}) {
  const listId = type === 'mysql' ? 'bkp-mysql-list' : 'bkp-pg-list';
  const item = document.createElement('div');
  item.dataset.dbtype = type;
  item.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;padding:6px;border:1px solid var(--border);border-radius:6px;background:rgba(0,0,0,.2);margin-bottom:4px;align-items:center;';
  item.innerHTML = `
    <input type="text"     placeholder="nom_bdd"   value="${escHtml(data.name||'')}"     style="width:100px;background:rgba(0,0,0,.3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;color:var(--text);font-family:var(--font-mono);font-size:.75rem;outline:none;" data-key="name" />
    <input type="text"     placeholder="user"      value="${escHtml(data.user||'root')}" style="width:80px; background:rgba(0,0,0,.3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;color:var(--text);font-family:var(--font-mono);font-size:.75rem;outline:none;" data-key="user" />
    <input type="password" placeholder="password"  value="${escHtml(data.password||'')}" style="width:100px;background:rgba(0,0,0,.3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;color:var(--text);font-family:var(--font-mono);font-size:.75rem;outline:none;" data-key="password" />
    <input type="text"     placeholder="127.0.0.1" value="${escHtml(data.host||'127.0.0.1')}" style="width:100px;background:rgba(0,0,0,.3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;color:var(--text);font-family:var(--font-mono);font-size:.75rem;outline:none;" data-key="host" />
    <input type="number"   placeholder="port"      value="${data.port||(type==='mysql'?3306:5432)}" style="width:55px; background:rgba(0,0,0,.3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;color:var(--text);font-family:var(--font-mono);font-size:.75rem;outline:none;" data-key="port" />
    <input type="text"     placeholder="container (opt.)" value="${escHtml(data.docker_container||'')}" style="width:130px;background:rgba(0,0,0,.3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;color:var(--text);font-family:var(--font-mono);font-size:.75rem;outline:none;" data-key="docker_container" />
    <button class="bkp-path-del" onclick="this.parentElement.remove()"><i class="fa-solid fa-xmark"></i></button>`;
  document.getElementById(listId).appendChild(item);
}

function getDbList(listId) {
  return Array.from(document.querySelectorAll(`#${listId} [data-dbtype]`)).map(item => {
    const obj = {};
    item.querySelectorAll('[data-key]').forEach(inp => { obj[inp.dataset.key] = inp.value.trim(); });
    return obj;
  });
}

function setPathList(listId, paths, placeholder) {
  document.getElementById(listId).innerHTML = '';
  (paths || []).forEach(p => addPathItem(listId, placeholder, p));
}

function updateDockerAllToggle() {
  const allChecked = document.getElementById('b-docker-all').checked;
  document.getElementById('bkp-docker-list-wrap').style.display = allChecked ? 'none' : '';
}
document.getElementById('b-docker-all').addEventListener('change', updateDockerAllToggle);
document.getElementById('b-subdir').addEventListener('input', function() {
  document.getElementById('b-subdir-preview').textContent = this.value || 'remote-vps';
});

async function loadBackupSettings() {
  if (!_selectedRemoteId) return;
  try {
    const d = await api(`/api/backup/settings/${_selectedRemoteId}`);
    const r = d, b = d.backup || {};
    document.getElementById('r-host').value           = r.host || '';
    document.getElementById('r-port').value           = r.port || 22;
    document.getElementById('r-user').value           = r.user || 'root';
    document.getElementById('r-auth').value           = r.auth_type || 'key';
    document.getElementById('r-key-path').value       = r.key_path || '/root/.ssh/id_rsa';
    document.getElementById('r-key-passphrase').value = r.key_passphrase || '';
    document.getElementById('r-password').value       = '';
    toggleAuthFields();
    const targets = b.targets || ['docker','websites','configs'];
    document.getElementById('t-docker').checked   = targets.includes('docker');
    document.getElementById('t-websites').checked = targets.includes('websites');
    document.getElementById('t-configs').checked  = targets.includes('configs');
    const subdir = b.subdir || 'remote-vps';
    document.getElementById('b-subdir').value = subdir;
    document.getElementById('b-subdir-preview').textContent = subdir;
    document.getElementById('b-compression').value = b.compression || 'gz';
    const mc = parseInt(b.max_count)||7;
    document.getElementById('b-max').value = mc; document.getElementById('b-max-label').textContent = mc;
    const md = parseInt(b.max_days)||0;
    document.getElementById('b-days').value = md; document.getElementById('b-days-label').textContent = md;
    document.getElementById('b-sched-enabled').checked = !!b.schedule_enabled;
    document.getElementById('b-schedule').value = b.schedule || '0 2 * * *';
    document.getElementById('b-docker-all').checked  = b.docker_all !== false;
    document.getElementById('b-docker-stop').checked = !!b.docker_stop;
    updateDockerAllToggle();
    setPathList('bkp-docker-list', b.docker_names||[], 'my-container');
    setPathList('bkp-web-list',    b.web_paths||['/var/www/html','/etc/nginx'], '/var/www/html');
    setPathList('bkp-cfg-list',    b.config_paths||['/etc/nginx','/etc/cron.d'], '/etc/nginx');
    setPathList('bkp-excl-list',   b.excludes||[], '*.log');
    document.getElementById('b-pre-hook').value  = b.pre_hook  || '';
    document.getElementById('b-post-hook').value = b.post_hook || '';
    document.getElementById('b-webhook').value   = b.webhook_url || '';
    document.getElementById('b-verify').checked  = !!b.verify;
    document.getElementById('bkp-mysql-list').innerHTML = '';
    document.getElementById('bkp-pg-list').innerHTML = '';
    const dbs = b.databases || {};
    (dbs.mysql   ||[]).forEach(e => addDbEntry('mysql',    e));
    (dbs.postgres||[]).forEach(e => addDbEntry('postgres', e));
  } catch(e) { toast('Erreur config backup: ' + e.message, 'err'); }
}

async function saveBackupSettings() {
  const btn = document.getElementById('bkp-save-btn'), ico = document.getElementById('bkp-save-ico');
  btn.disabled = true; ico.className = 'fa-solid fa-rotate spin';
  const targets = [];
  if (document.getElementById('t-docker').checked)   targets.push('docker');
  if (document.getElementById('t-websites').checked) targets.push('websites');
  if (document.getElementById('t-configs').checked)  targets.push('configs');
  const mysqlList = getDbList('bkp-mysql-list');
  const pgList    = getDbList('bkp-pg-list');
  const body = {
    host: document.getElementById('r-host').value.trim(),
    port: parseInt(document.getElementById('r-port').value)||22,
    user: document.getElementById('r-user').value.trim()||'root',
    auth_type:      document.getElementById('r-auth').value,
    key_path:       document.getElementById('r-key-path').value.trim(),
    key_passphrase: document.getElementById('r-key-passphrase').value,
    password:       document.getElementById('r-password').value || '**hidden**',
    backup: {
      targets,
      subdir:           document.getElementById('b-subdir').value.trim()||'remote-vps',
      compression:      document.getElementById('b-compression').value,
      max_count:        parseInt(document.getElementById('b-max').value)||7,
      max_days:         parseInt(document.getElementById('b-days').value)||0,
      schedule_enabled: document.getElementById('b-sched-enabled').checked,
      schedule:         document.getElementById('b-schedule').value.trim(),
      docker_all:       document.getElementById('b-docker-all').checked,
      docker_stop:      document.getElementById('b-docker-stop').checked,
      docker_names:     getPathList('bkp-docker-list'),
      web_paths:        getPathList('bkp-web-list'),
      config_paths:     getPathList('bkp-cfg-list'),
      excludes:         getPathList('bkp-excl-list'),
      pre_hook:         document.getElementById('b-pre-hook').value.trim(),
      post_hook:        document.getElementById('b-post-hook').value.trim(),
      webhook_url:      document.getElementById('b-webhook').value.trim(),
      verify:           document.getElementById('b-verify').checked,
      databases:        {mysql: mysqlList, postgres: pgList},
    }
  };
  if (!_selectedRemoteId) { toast("Sélectionnez un remote d'abord", 'err'); return; }
  try {
    await api(`/api/backup/settings/${_selectedRemoteId}`, {method:'POST', body});
    toast('Configuration sauvegardée', 'ok');
    refreshRemoteCards();
  } catch(e) { toast(e.message, 'err'); }
  btn.disabled = false; ico.className = 'fa-solid fa-floppy-disk';
}

async function testConnection() {
  if (!_selectedRemoteId) return;
  const btn = document.getElementById('bkp-test-btn'), ico = document.getElementById('bkp-test-ico');
  const out = document.getElementById('bkp-test-out');
  btn.disabled = true; ico.className = 'fa-solid fa-rotate spin'; out.style.display = 'none';
  try {
    const d = await api(`/api/backup/test/${_selectedRemoteId}`, {method:'POST', body:{}});
    out.style.display = '';
    if (d.ok) {
      out.style.color = 'var(--up)';
      out.textContent = '✓ Connexion réussie\n' + (d.output||'') + (d.disk ? '\nDisque: '+d.disk : '');
      toast('Connexion SSH établie', 'ok');
    } else {
      out.style.color = 'var(--down)'; out.textContent = '✗ ' + (d.error||'Erreur inconnue');
      toast('Connexion échouée', 'err');
    }
  } catch(e) { out.style.display=''; out.style.color='var(--down)'; out.textContent='✗ '+e.message; toast(e.message,'err'); }
  btn.disabled = false; ico.className = 'fa-solid fa-plug';
}

async function probeDockerContainers() {
  const ico  = document.getElementById('bkp-probe-ico');
  const wrap = document.getElementById('bkp-docker-detected');
  const list = document.getElementById('bkp-docker-detected-list');
  ico.className = 'fa-solid fa-rotate spin';
  try {
    const d = await api(`/api/backup/docker-containers/${_selectedRemoteId}`, {method:'POST', body:{}});
    if (d.ok && d.containers?.length) {
      wrap.style.display = '';
      list.innerHTML = d.containers.map(c =>
        `<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border);">
          <i class="fa-brands fa-docker" style="color:var(--accent);font-size:.75rem;"></i>
          <span style="flex:1;font-family:var(--font-mono);font-size:.75rem;">${escHtml(c.name)}</span>
          <span style="color:var(--text-muted);font-size:.62rem;">${escHtml(c.image)}</span>
          <button class="btn-sm" style="padding:2px 7px;" onclick="addPathItem('bkp-docker-list','container-name','${escHtml(c.name)}')">
            <i class="fa-solid fa-plus"></i>
          </button>
        </div>`).join('');
      toast(`${d.containers.length} container(s) détectés`, 'ok');
    } else { toast(d.error||'Aucun container', d.ok?'info':'err'); }
  } catch(e) { toast(e.message,'err'); }
  ico.className = 'fa-solid fa-magnifying-glass';
}

async function runBackup() {
  if (!_selectedRemoteId) return;
  const btn = document.getElementById('bkp-run-btn'), ico = document.getElementById('bkp-run-ico');
  btn.disabled = true; ico.className = 'fa-solid fa-rotate spin';
  try {
    const d = await api(`/api/backup/run/${_selectedRemoteId}`, {method:'POST', body:{}});
    toast(d.message||(d.ok?'Backup démarré':'Erreur'), d.ok?'ok':'err');
    if (d.ok) startBkpPoll();
  } catch(e) { toast(e.message,'err'); }
  btn.disabled = false; ico.className = 'fa-solid fa-play';
}

function startBkpPoll() { if (!_bkpPollId) _bkpPollId = setInterval(refreshBackupStatus, 2000); }
function stopBkpPoll()  { if (_bkpPollId) { clearInterval(_bkpPollId); _bkpPollId = null; } }

async function refreshBackupStatus() {
  if (!_selectedRemoteId) return;
  try {
    const d = await api(`/api/backup/status/${_selectedRemoteId}`);
    const depWarn = document.getElementById('bkp-dep-warn'), depText = document.getElementById('bkp-dep-text');
    const missing = [...(!d.has_paramiko?['paramiko']:[]), ...(!d.has_scheduler?['apscheduler']:[])];
    if (missing.length) {
      depText.textContent = `Dépendances manquantes: ${missing.join(', ')} — pip install ${missing.join(' ')}`;
      depWarn.style.display = 'flex';
    } else { depWarn.style.display = 'none'; }

    const dot = document.getElementById('bkp-dot'), text = document.getElementById('bkp-status-text');
    const progWrap = document.getElementById('bkp-progress-wrap');
    const progFill = document.getElementById('bkp-progress-fill'), progPct = document.getElementById('bkp-progress-pct');
    const progLbl  = document.getElementById('bkp-progress-label');

    if (d.running) {
      dot.className = 'bkp-status-dot running';
      text.textContent = '⟳ ' + (d.progress||'En cours…');
      progWrap.style.display = '';
      const pct = d.percent||0;
      progFill.style.width = pct+'%'; progPct.textContent = pct+'%'; progLbl.textContent = d.progress||'En cours…';
      startBkpPoll();
    } else {
      stopBkpPoll(); progWrap.style.display = 'none';
      if (d.last_status==='ok') {
        dot.className = 'bkp-status-dot ok';
        text.textContent = '✓ Backup réussi — ' + (d.last_run||'').replace('T',' ').slice(0,19);
      } else if (d.last_status==='error') {
        dot.className = 'bkp-status-dot error';
        text.textContent = '✗ Backup échoué — ' + (d.last_run||'').replace('T',' ').slice(0,19);
      } else {
        dot.className = 'bkp-status-dot';
        text.textContent = d.last_run ? 'Dernier: '+(d.last_run||'').replace('T',' ').slice(0,19) : 'Aucun backup lancé';
      }
    }
    const log = (d.log||[]).join('\n');
    if (log) { const box = document.getElementById('bkp-log-box'); box.textContent = log; box.scrollTop = box.scrollHeight; }
    if (!d.running && d.last_status !== null) refreshBackupList();
  } catch { /* silent */ }
}

async function refreshBackupList() {
  if (!_selectedRemoteId) return;
  try {
    const d = await api(`/api/backup/list/${_selectedRemoteId}`);
    const tbody = document.getElementById('bkp-history-tbody');
    const sel   = document.getElementById('restore-bkp-id');
    if (!d.backups?.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="tbl-empty">Aucun backup trouvé</td></tr>';
      sel.innerHTML = '<option value="">— aucun backup —</option>'; return;
    }
    const sColor = {ok:'var(--up)', error:'var(--down)', unknown:'var(--text-muted)'};
    const sIcon  = {ok:'fa-circle-check', error:'fa-circle-xmark', unknown:'fa-circle'};
    tbody.innerHTML = d.backups.map(b => `<tr>
      <td class="mono" style="font-size:.70rem;">${escHtml(b.id)}</td>
      <td style="font-family:var(--font-mono);font-size:.68rem;color:var(--text-muted);">${escHtml(b.size)}</td>
      <td style="font-family:var(--font-mono);font-size:.68rem;color:var(--text-muted);">${escHtml(b.mtime)}</td>
      <td><i class="fa-solid ${sIcon[b.status]||'fa-circle'}" style="color:${sColor[b.status]||'var(--text-muted)'};font-size:.75rem;"></i></td>
      <td style="font-family:var(--font-mono);font-size:.60rem;color:var(--text-muted);">${escHtml(b.targets||'')}</td>
      <td><div style="display:flex;gap:3px;">
        <button class="btn-sm" onclick="showManifest('${escHtml(b.id)}')" title="Manifest"><i class="fa-solid fa-list"></i></button>
        <button class="btn-sm danger" onclick="deleteBackup('${escHtml(b.id)}')" title="Supprimer"><i class="fa-solid fa-trash"></i></button>
      </div></td>
    </tr>`).join('');
    sel.innerHTML = '<option value="">— sélectionner —</option>' +
      d.backups.map(b => `<option value="${escHtml(b.id)}">${escHtml(b.id)} (${escHtml(b.size)})</option>`).join('');

    const chartWrap = document.getElementById('bkp-chart-wrap');
    if (d.backups.length > 1) {
      chartWrap.style.display = '';
      const labels = d.backups.map(b => b.mtime.slice(0, 10)).reverse();
      const sizes  = d.backups.map(b => +(b.size_bytes / 1024 / 1024).toFixed(1)).reverse();
      if (_bkpChart) { _bkpChart.destroy(); _bkpChart = null; }
      const ctx = document.getElementById('bkp-chart').getContext('2d');
      _bkpChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: 'Taille (MB)',
            data: sizes,
            borderColor: 'rgba(0,200,255,0.8)',
            backgroundColor: 'rgba(0,200,255,0.08)',
            pointBackgroundColor: 'rgba(0,200,255,1)',
            pointRadius: 4, fill: true, tension: 0.3,
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: '#55667a', font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(0,200,255,0.05)' } },
            y: { ticks: { color: '#55667a', font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(0,200,255,0.05)' }, beginAtZero: true }
          }
        }
      });
    } else { chartWrap.style.display = 'none'; }
  } catch(e) { toast('Erreur liste backups: ' + e.message, 'err'); }
}

async function showManifest(id) {
  try {
    const d = await api(`/api/backup/manifest/${_selectedRemoteId}/${encodeURIComponent(id)}`);
    document.getElementById('modal-title').textContent = 'Manifest — ' + id;
    document.getElementById('modal-sub').textContent   = '';
    document.getElementById('modal-fields').innerHTML  =
      `<textarea class="code" style="min-height:280px;font-size:.70rem;" readonly>${escHtml(JSON.stringify(d,null,2))}</textarea>`;
    document.getElementById('modal-confirm').style.display = 'none';
    document.getElementById('modal-overlay').classList.add('open');
  } catch(e) { toast('Manifest introuvable', 'err'); }
}

async function deleteBackup(id) {
  if (!confirm(`Supprimer ${id} ? Irréversible.`)) return;
  try {
    await api(`/api/backup/delete/${_selectedRemoteId}`, {method:'POST', body:{id}});
    toast('Backup supprimé', 'ok'); refreshBackupList();
  } catch(e) { toast(e.message,'err'); }
}

async function loadRestoreContents() {
  const id  = document.getElementById('restore-bkp-id').value;
  const arc = document.getElementById('restore-arc');
  arc.innerHTML = '<option value="">Chargement...</option>';
  if (!id) { arc.innerHTML = "<option value=''>— sélectionner d'abord un backup —</option>"; return; }
  try {
    const d = await api(`/api/backup/contents/${_selectedRemoteId}/${encodeURIComponent(id)}`);
    const archives = (d.files||[]).filter(f => /\.(tar\.gz|tar\.bz2|tar|sql\.gz)$/.test(f.path));
    arc.innerHTML = '<option value="">— sélectionner —</option>' +
      archives.map(f => `<option value="${escHtml(f.path)}">${escHtml(f.path)} (${escHtml(f.size)})</option>`).join('');
  } catch(e) { arc.innerHTML = '<option value="">Erreur chargement</option>'; }
}

async function runRestore() {
  const backup_id = document.getElementById('restore-bkp-id').value;
  const archive   = document.getElementById('restore-arc').value;
  const dest      = document.getElementById('restore-dest').value.trim() || '/tmp/restore';
  if (!backup_id || !archive) { toast('Sélectionnez un backup et une archive', 'err'); return; }
  const btn = document.getElementById('restore-btn'), ico = document.getElementById('restore-ico');
  const res = document.getElementById('restore-result');
  btn.disabled = true; ico.className = 'fa-solid fa-rotate spin'; res.textContent = 'Restauration en cours…';
  try {
    const d = await api(`/api/backup/restore/${_selectedRemoteId}`, {method:'POST', body:{backup_id, archive, dest}});
    res.style.color = d.ok ? 'var(--up)' : 'var(--down)';
    res.textContent = d.message || (d.ok ? '✓ Restauré' : '✗ Erreur');
    toast(d.message||(d.ok?'Restauration réussie':'Erreur restauration'), d.ok?'ok':'err');
  } catch(e) { res.style.color='var(--down)'; res.textContent='✗ '+e.message; toast(e.message,'err'); }
  btn.disabled = false; ico.className = 'fa-solid fa-clock-rotate-left';
}

// ─── User management ─────────────────────────────────────────────────────
async function refreshUsers() {
  try {
    const d = await api('/api/users');
    const tbody = document.getElementById('users-tbody');
    if (!tbody) return;
    if (!d.users?.length) { tbody.innerHTML = '<tr><td colspan="3" class="tbl-empty">Aucun utilisateur</td></tr>'; return; }
    tbody.innerHTML = d.users.map(u => `<tr>
      <td class="mono">${escHtml(u.username)}</td>
      <td><span class="role-badge ${u.role}">${u.role === 'admin' ? '<i class="fa-solid fa-shield-halved"></i> admin' : '<i class="fa-solid fa-eye"></i> readonly'}</span></td>
      <td><div style="display:flex;gap:4px;">
        <button class="btn-sm" onclick="openModal('user-role','${escHtml(u.username)}|${u.role}')"><i class="fa-solid fa-user-gear"></i></button>
        <button class="btn-sm danger" onclick="openModal('user-del','${escHtml(u.username)}')"><i class="fa-solid fa-trash"></i></button>
      </div></td>
    </tr>`).join('');
  } catch { /* silent */ }
}

// ─── Remote add/edit modal helpers ────────────────────────────────────────
let _editRemoteData = {};

async function openEditRemote(id) {
  _editRemoteData = { id };
  try {
    const d = await api(`/api/backup/settings/${id}`);
    _editRemoteData = d;
  } catch { }
  openModal('remote-edit');
}

// ─── Terminal ──────────────────────────────────────────────────────────────
let _term = null, _termWs = null, _termFitAddon = null;
let _termInitialized = false;

function initTerminalTab() {
  if (!_termInitialized) {
    _termInitialized = true;
    if (typeof Terminal === 'undefined') {
      document.getElementById('term-sock-warn').style.display = '';
      document.getElementById('term-sock-warn').textContent = ' ⚠ xterm.js non chargé (vérifiez votre connexion internet).';
      return;
    }
    _term = new Terminal({
      theme: { background: '#0d1117', foreground: '#dde4f0', cursor: '#00c8ff', selectionBackground: 'rgba(0,200,255,0.2)' },
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      fontSize: 13, cursorBlink: true, scrollback: 5000,
    });
    _termFitAddon = new FitAddon.FitAddon();
    _term.loadAddon(_termFitAddon);
    _term.open(document.getElementById('term-container'));
    _termFitAddon.fit();
    _term.writeln('\x1b[36m  NXSlab Terminal — sélectionnez un VPS et cliquez Connecter\x1b[0m');
    window.addEventListener('resize', () => { if (_termFitAddon) _termFitAddon.fit(); });
  }
  refreshRemoteCards();
}

function termConnect() {
  const rid = document.getElementById('term-remote-sel').value;
  if (!rid) { toast('Sélectionnez un VPS', 'err'); return; }
  if (_termWs) { _termWs.close(); _termWs = null; }
  if (!_term) { initTerminalTab(); }

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const wsUrl = `${proto}://${location.host}/ws/terminal/${rid}`;

  const status = document.getElementById('term-status');
  status.textContent = 'Connexion…';
  document.getElementById('term-connect-btn').style.display = 'none';
  document.getElementById('term-disconnect-btn').style.display = '';

  try {
    _termWs = new WebSocket(wsUrl);
    _termWs.onopen = () => {
      status.textContent = 'Connecté';
      _term.focus();
      if (_termFitAddon) _termFitAddon.fit();
      _termWs.send(JSON.stringify({type:'resize', cols: _term.cols, rows: _term.rows}));
      _term.onData(data => { if (_termWs && _termWs.readyState === WebSocket.OPEN) _termWs.send(data); });
      _term.onResize(size => { if (_termWs && _termWs.readyState === WebSocket.OPEN) _termWs.send(JSON.stringify({type:'resize', cols:size.cols, rows:size.rows})); });
    };
    _termWs.onmessage = e => { if (_term) _term.write(e.data); };
    _termWs.onerror   = () => { status.textContent = 'Erreur WebSocket'; };
    _termWs.onclose   = () => {
      status.textContent = 'Déconnecté';
      document.getElementById('term-connect-btn').style.display = '';
      document.getElementById('term-disconnect-btn').style.display = 'none';
      if (_term) _term.writeln('\r\n\x1b[33m[Connexion fermée]\x1b[0m');
    };
  } catch(e) {
    status.textContent = 'WebSocket non supporté';
    document.getElementById('term-sock-warn').style.display = '';
  }
}

function termDisconnect() {
  if (_termWs) { _termWs.close(); _termWs = null; }
}

// ─── Init ─────────────────────────────────────────────────────────────────
(async () => {
  await refreshStatus();
  await refreshSystem();
  try {
    const me = await api('/api/settings/me');
    if (me.username) {
      const badge = document.getElementById('nav-user-badge');
      const uEl   = document.getElementById('nav-username');
      if (badge) badge.style.display = '';
      if (uEl)   uEl.textContent = me.username;
    }
    refreshUsers();
  } catch { /* silent */ }
  refreshBackupSummary();
  refreshAllRemoteStats();
  setInterval(() => { refreshBackupSummary(); refreshAllRemoteStats(); }, 60000);
})();
