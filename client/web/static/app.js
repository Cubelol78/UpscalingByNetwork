/* ============================================================
   Upscaling Client — Web UI JavaScript
   ============================================================ */

'use strict';

// ── SVG ICONS (inline) ───────────────────────────────────────
const _svgDot = '<svg class="icon" width="8" height="8" viewBox="0 0 8 8"><circle cx="4" cy="4" r="4" fill="currentColor"/></svg>';
const _svgDotBig = '<svg class="icon" width="10" height="10" viewBox="0 0 8 8"><circle cx="4" cy="4" r="4" fill="currentColor"/></svg>';
const _svgCheck = '<svg class="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
const _svgCross = '<svg class="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

let _ws = null;
let _wsReconnectTimeout = null;
let _perfSaveTimeout = null;
let _webhookSaveTimeout = null;
let _lastState = null;

// ── INIT ─────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  restoreTab();
  startWebSocket();
  loadPerfConfig();
  loadWebhookConfig();
});

// ── API HELPER ────────────────────────────────────────────────
async function apiFetch(url, opts = {}) {
  opts.headers = opts.headers || {};
  if (!opts.headers['Content-Type'] && opts.body) opts.headers['Content-Type'] = 'application/json';
  try { return await fetch(url, opts); }
  catch (e) { console.warn('apiFetch error:', url, e); return null; }
}

// ── WEBSOCKET ─────────────────────────────────────────────────
function startWebSocket() {
  if (_ws) _ws.close();
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  _ws = new WebSocket(`${proto}://${location.host}/ws`);

  _ws.onopen = () => {
    updateWsDot(true);
    if (_wsReconnectTimeout) { clearTimeout(_wsReconnectTimeout); _wsReconnectTimeout = null; }
  };

  _ws.onmessage = (evt) => {
    try {
      const state = JSON.parse(evt.data);
      _lastState = state;
      renderState(state);
    } catch (e) { console.error('renderState error:', e); }
  };

  _ws.onclose = () => {
    updateWsDot(false);
    _wsReconnectTimeout = setTimeout(startWebSocket, 2000);
  };

  _ws.onerror = () => _ws.close();
}

function updateWsDot(ok) {
  const dot = document.getElementById('ws-dot');
  const lbl = document.getElementById('ws-label');
  if (ok) { dot.className = 'ws-dot connected'; lbl.textContent = 'Temps réel'; }
  else     { dot.className = 'ws-dot';            lbl.textContent = 'Déconnecté'; }
}

// ── RENDER ────────────────────────────────────────────────────
function renderState(state) {
  const status = state.status || {};
  renderConnectionTab(status);
  renderMonitoringTab(status, state.logs || []);
  renderServersTab(state.servers || {});
}

function renderConnectionTab(status) {
  const connected = status.connected || false;
  const st = status.status || 'disconnected';

  // Badge header
  const badge = document.getElementById('conn-badge');
  badge.className = connected ? 'connected' : (st === 'connecting' ? 'connecting' : 'disconnected');
  badge.innerHTML = connected
    ? `${_svgDot} ${escHtml(status.server_address || 'Connecté')}`
    : (st === 'connecting' ? `${_svgDot} Connexion...` : `${_svgDot} Déconnecté`);

  // Big status
  const big = document.getElementById('conn-status-big');
  const addr = document.getElementById('conn-server-addr');
  if (connected) {
    big.innerHTML = `${_svgDotBig} Connecté`;
    big.style.color = 'var(--success)';
    addr.textContent = `${status.server_address || ''}:${status.control_port || ''}`;
  } else {
    big.innerHTML = st === 'connecting' ? `${_svgDotBig} Connexion en cours...` : `${_svgDotBig} Déconnecté`;
    big.style.color = st === 'connecting' ? 'var(--warning)' : 'var(--danger)';
    addr.textContent = '';
  }

  // Boutons
  const btnDisconnect = document.getElementById('btn-disconnect');
  const formCard = document.getElementById('connect-form-card');
  if (connected) {
    btnDisconnect.style.display = 'inline-flex';
    formCard.style.display = 'none';
  } else {
    btnDisconnect.style.display = 'none';
    formCard.style.display = 'block';
  }
}

function renderMonitoringTab(status, logs) {
  setText('stat-batches-ok', status.batches_processed ?? 0);
  setText('stat-batches-fail', status.batches_failed ?? 0);
  setText('stat-images', status.images_processed ?? 0);
  setText('stat-queue', status.queue_size ?? 0);

  // Badge statut
  const st = status.status || 'disconnected';
  const statusBadge = document.getElementById('current-status-badge');
  statusBadge.className = `badge badge-${st}`;
  statusBadge.textContent = st;

  // Batch en cours
  const batchId = status.current_batch || '';
  setText('current-batch-id', batchId ? `Batch: ${batchId.slice(0, 12)}...` : '');

  const progress = status.batch_progress || 0;
  const total = status.batch_total || 0;
  const pct = total > 0 ? Math.round(progress / total * 100) : 0;
  const progressEl = document.getElementById('batch-progress');
  if (progressEl) progressEl.value = pct;
  setText('batch-progress-label', total > 0 ? `${progress} / ${total} images` : '—');

  // Logs
  renderLogs(logs);
}

function renderLogs(logs) {
  const container = document.getElementById('log-container');
  if (!logs || !logs.length) {
    container.innerHTML = '<div class="log-entry" style="color:var(--text2)">Aucun log disponible</div>';
    return;
  }

  const wasAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 20;
  container.innerHTML = logs.slice(-50).map(log => {
    const level = (log.level || 'info').toLowerCase();
    const levelClass = level === 'error' ? 'log-error' : (level === 'warning' || level === 'warn' ? 'log-warning' : 'log-info');
    const time = log.time || log.timestamp || '';
    const msg = escHtml(log.message || log.msg || String(log));
    return `<div class="log-entry"><span class="log-time">${escHtml(time)} </span><span class="${levelClass}">${msg}</span></div>`;
  }).join('');

  if (wasAtBottom) container.scrollTop = container.scrollHeight;
}

function renderServersTab(servers) {
  const tbody = document.getElementById('servers-tbody');
  const select = document.getElementById('saved-server-select');
  const entries = Object.entries(servers);

  // Table
  if (!entries.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="no-data">Aucun serveur sauvegardé</td></tr>';
  } else {
    tbody.innerHTML = entries.map(([name, srv]) => `
      <tr>
        <td><strong>${escHtml(name)}</strong></td>
        <td>${escHtml(srv.host || '')}</td>
        <td>${escHtml(String(srv.port || ''))}</td>
        <td>${srv.password ? '••••••' : '—'}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="connectToSaved('${escHtml(name)}')">Connecter</button>
          <button class="btn btn-danger btn-sm" onclick="deleteSavedServer('${escHtml(name)}')">Supprimer</button>
        </td>
      </tr>
    `).join('');
  }

  // Select dans l'onglet Connexion
  const currentVal = select.value;
  select.innerHTML = '<option value="">— Choisir un serveur sauvegardé —</option>';
  entries.forEach(([name]) => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  });
  if (currentVal) select.value = currentVal;
}

// ── CONNEXION ─────────────────────────────────────────────────
function loadSavedServer() {
  const name = document.getElementById('saved-server-select').value;
  const saveGroup = document.getElementById('conn-save-group');
  const saveCheckbox = document.getElementById('conn-save');

  if (!name) {
    // Saisie manuelle — afficher la checkbox
    if (saveGroup) saveGroup.style.display = 'flex';
    if (saveCheckbox) { saveCheckbox.disabled = false; saveCheckbox.checked = false; }
    return;
  }

  if (!_lastState) return;
  const srv = (_lastState.servers || {})[name];
  if (!srv) return;
  setVal('conn-host', srv.host || '');
  setVal('conn-port', srv.port || 8765);
  setVal('conn-password', srv.password || '');

  // Masquer la checkbox — ce serveur est déjà sauvegardé
  if (saveGroup) saveGroup.style.display = 'none';
  if (saveCheckbox) saveCheckbox.checked = false;
}

async function doConnect() {
  const host = getVal('conn-host').trim();
  const port = parseInt(getVal('conn-port')) || 8765;
  const password = getVal('conn-password');
  const errEl = document.getElementById('conn-error');
  errEl.style.display = 'none';

  if (!host) {
    errEl.textContent = 'Veuillez saisir une adresse IP ou hostname.';
    errEl.style.display = 'block';
    return;
  }

  const body = { host, port, password };
  const res = await apiFetch('/api/connect', { method: 'POST', body: JSON.stringify(body) });

  if (res && res.ok) {
    // Sauvegarder si demandé et pas déjà sauvegardé
    if (document.getElementById('conn-save').checked && host && !_isServerAlreadySaved(host, port)) {
      const name = `${host}:${port}`;
      await apiFetch('/api/servers', {
        method: 'POST',
        body: JSON.stringify({ name, host, port, password })
      });
    }
    showToast('Connexion en cours...');
  } else {
    const data = res ? await res.json().catch(() => ({})) : {};
    errEl.textContent = data.detail || 'Erreur de connexion.';
    errEl.style.display = 'block';
  }
}

async function doDisconnect() {
  if (!confirm('Déconnecter du serveur ?')) return;
  await apiFetch('/api/disconnect', { method: 'POST' });
  showToast('Déconnecté');
}

async function connectToSaved(name) {
  if (!_lastState) return;
  const srv = (_lastState.servers || {})[name];
  if (!srv) return;
  const body = { host: srv.host, port: srv.port || 8765, password: srv.password || '' };
  const res = await apiFetch('/api/connect', { method: 'POST', body: JSON.stringify(body) });
  if (res && res.ok) showToast('Connexion en cours...');
  else showToast('Erreur de connexion', true);
}

function _isServerAlreadySaved(host, port) {
  if (!_lastState || !_lastState.servers) return false;
  for (const [name, srv] of Object.entries(_lastState.servers)) {
    if (srv.host === host && srv.port === port) return true;
  }
  return false;
}

// ── GESTION SERVEURS ──────────────────────────────────────────
function showAddServerModal() { document.getElementById('add-server-modal').style.display = 'flex'; }
function closeAddServerModal() { document.getElementById('add-server-modal').style.display = 'none'; }

async function addServer() {
  const name = getVal('srv-name').trim();
  const host = getVal('srv-host').trim();
  const port = parseInt(getVal('srv-port')) || 8765;
  const password = getVal('srv-password');

  if (!name || !host) { showToast('Nom et adresse requis', true); return; }

  const res = await apiFetch('/api/servers', {
    method: 'POST',
    body: JSON.stringify({ name, host, port, password })
  });
  if (res && res.ok) { closeAddServerModal(); showToast('Serveur ajouté'); }
  else showToast('Erreur', true);
}

async function deleteSavedServer(name) {
  if (!confirm(`Supprimer "${name}" ?`)) return;
  const res = await apiFetch(`/api/servers/${encodeURIComponent(name)}`, { method: 'DELETE' });
  if (res && res.ok) showToast('Serveur supprimé');
}

// ── PERFORMANCE ───────────────────────────────────────────────
async function loadPerfConfig() {
  const res = await apiFetch('/api/config');
  if (!res || !res.ok) return;
  const cfg = await res.json();
  setVal('cfg-tile-size', cfg.tile_size || 512);
  setVal('cfg-load-threads', cfg.load_threads || 2);
  setVal('cfg-process-threads', cfg.process_threads || 4);
  setVal('cfg-save-threads', cfg.save_threads || 2);
  setVal('cfg-work-dir', cfg.work_directory || './work');
}

function schedulePerfSave() {
  if (_perfSaveTimeout) clearTimeout(_perfSaveTimeout);
  _perfSaveTimeout = setTimeout(savePerfConfig, 500);
}

async function savePerfConfig() {
  const params = {
    tile_size: parseInt(getVal('cfg-tile-size')) || 512,
    load_threads: parseInt(getVal('cfg-load-threads')) || 2,
    process_threads: parseInt(getVal('cfg-process-threads')) || 4,
    save_threads: parseInt(getVal('cfg-save-threads')) || 2,
    work_directory: getVal('cfg-work-dir')
  };
  const res = await apiFetch('/api/config', { method: 'PUT', body: JSON.stringify({ params }) });
  if (res && res.ok) {
    const ind = document.getElementById('perf-save-indicator');
    ind.classList.add('show');
    setTimeout(() => ind.classList.remove('show'), 2000);
  }
}

// ── WEBHOOKS ──────────────────────────────────────────────────
async function loadWebhookConfig() {
  const res = await apiFetch('/api/webhooks');
  if (!res || !res.ok) return;
  const wh = await res.json();
  document.getElementById('wh-enabled').checked = wh.enabled || false;
  setVal('wh-url', wh.url || '');
}

function scheduleWebhookSave() {
  if (_webhookSaveTimeout) clearTimeout(_webhookSaveTimeout);
  _webhookSaveTimeout = setTimeout(saveWebhook, 500);
}

async function saveWebhook() {
  await apiFetch('/api/webhooks', {
    method: 'PUT',
    body: JSON.stringify({
      enabled: document.getElementById('wh-enabled').checked,
      url: getVal('wh-url'),
      events: ''
    })
  });
}

async function testWebhook() {
  const res = await apiFetch('/api/webhooks/test', { method: 'POST' });
  const el = document.getElementById('wh-test-result');
  if (res && res.ok) {
    const d = await res.json();
    el.style.color = d.success ? 'var(--success)' : 'var(--danger)';
    el.innerHTML = d.success
      ? `${_svgCheck} Webhook envoyé`
      : `${_svgCross} ${escHtml(d.error || 'Erreur')}`;
  } else {
    el.style.color = 'var(--danger)';
    el.innerHTML = `${_svgCross} Erreur réseau`;
  }
  setTimeout(() => { el.innerHTML = ''; }, 4000);
}

// ── TAB NAVIGATION ────────────────────────────────────────────
function switchTab(name, btn) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  localStorage.setItem('client_web_tab', name);
}

function restoreTab() {
  const tab = localStorage.getItem('client_web_tab');
  if (!tab) return;
  const btn = [...document.querySelectorAll('.tab-btn')].find(b =>
    b.getAttribute('onclick') && b.getAttribute('onclick').includes(`'${tab}'`));
  if (btn) btn.click();
}

// ── UTILITAIRES ───────────────────────────────────────────────
function escHtml(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function setVal(id, val)  { const el = document.getElementById(id); if (el) el.value = val; }
function getVal(id)       { const el = document.getElementById(id); return el ? el.value : ''; }

function showToast(msg, error = false) {
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:var(--radius-sm);
    background:${error ? 'rgba(224,82,82,0.85)' : 'rgba(76,175,120,0.85)'};
    backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
    color:#fff;font-size:13px;font-weight:600;z-index:9999;
    box-shadow:0 8px 32px rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.1);
    animation:fadeSlideIn .3s ease;`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}
