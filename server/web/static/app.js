/* ============================================================
   Upscaling Server — Web UI JavaScript
   WebSocket + fetch API + rendu dynamique des tabs
   ============================================================ */

'use strict';

// ── TOKEN & AUTH ──────────────────────────────────────────────
let _token = localStorage.getItem('server_web_token') || '';
let _wsConnected = false;
let _ws = null;
let _wsReconnectTimeout = null;
let _configSaveTimeout = null;
let _webhookSaveTimeout = null;

// ── INIT ─────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  restoreTab();
  await checkAuth();
});

async function checkAuth() {
  const res = await apiFetch('/api/auth/check', { method: 'GET' });
  if (!res) { showLogin(); return; }
  const data = await res.json();
  if (data.valid || data.no_password) {
    if (data.no_password) _token = 'no-auth';
    hideLogin();
    startWebSocket();
    loadConfig();
    loadWebhooks();
  } else {
    showLogin();
  }
}

function showLogin() {
  document.getElementById('login-overlay').style.display = 'flex';
  setTimeout(() => document.getElementById('login-password').focus(), 100);
}

function hideLogin() {
  document.getElementById('login-overlay').style.display = 'none';
}

async function doLogin() {
  const pwd = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.style.display = 'none';

  const res = await fetch('/api/auth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: pwd })
  });

  if (res.ok) {
    const data = await res.json();
    _token = data.token;
    localStorage.setItem('server_web_token', _token);
    hideLogin();
    startWebSocket();
    loadConfig();
    loadWebhooks();
  } else {
    errEl.textContent = 'Mot de passe incorrect.';
    errEl.style.display = 'block';
  }
}

document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && document.getElementById('login-overlay').style.display !== 'none') {
    doLogin();
  }
});

// ── API HELPER ────────────────────────────────────────────────
async function apiFetch(url, opts = {}) {
  opts.headers = opts.headers || {};
  if (_token && _token !== 'no-auth') {
    opts.headers['Authorization'] = `Bearer ${_token}`;
  }
  if (!opts.headers['Content-Type'] && opts.body) {
    opts.headers['Content-Type'] = 'application/json';
  }
  try {
    return await fetch(url, opts);
  } catch (e) {
    console.warn('apiFetch error:', e);
    return null;
  }
}

// ── WEBSOCKET ─────────────────────────────────────────────────
function startWebSocket() {
  if (_ws) { _ws.close(); }

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${location.host}/ws?token=${encodeURIComponent(_token)}`;

  _ws = new WebSocket(url);

  _ws.onopen = () => {
    _wsConnected = true;
    updateWsDot(true);
    if (_wsReconnectTimeout) { clearTimeout(_wsReconnectTimeout); _wsReconnectTimeout = null; }
  };

  _ws.onmessage = (evt) => {
    try {
      const state = JSON.parse(evt.data);
      renderState(state);
    } catch (e) {}
  };

  _ws.onclose = () => {
    _wsConnected = false;
    updateWsDot(false);
    _wsReconnectTimeout = setTimeout(startWebSocket, 2000);
  };

  _ws.onerror = () => { _ws.close(); };
}

function updateWsDot(connected) {
  const dot = document.getElementById('ws-dot');
  const lbl = document.getElementById('ws-label');
  if (connected) { dot.className = 'ws-dot connected'; lbl.textContent = 'Temps réel'; }
  else           { dot.className = 'ws-dot';            lbl.textContent = 'Déconnecté'; }
}

// ── RENDER STATE (depuis WebSocket) ──────────────────────────
function renderState(state) {
  // Header badge
  const badge = document.getElementById('server-status-badge');
  if (state.server_running) {
    badge.className = 'running';
    badge.textContent = `● En cours (${state.uptime_str || ''})`;
  } else {
    badge.className = 'stopped';
    badge.textContent = '● Arrêté';
  }

  // Dashboard
  if (state.dashboard) renderDashboard(state.dashboard, state.uptime_str);
  // Clients
  if (state.clients) renderClients(state.clients);
  // Jobs
  if (state.jobs) renderJobs(state.jobs);
}

// ── DASHBOARD ─────────────────────────────────────────────────
function renderDashboard(d, uptime) {
  setText('stat-clients', d.active_clients ?? 0);
  setText('stat-queued', d.videos_queued ?? 0);
  setText('stat-processing', d.videos_processing ?? 0);
  setText('stat-batches-pending', d.batches_pending ?? 0);
  setText('stat-batches-done', d.batches_completed ?? 0);
  setText('stat-uptime', uptime || '—');

  const list = document.getElementById('activity-list');
  const activities = d.recent_activity || [];
  if (!activities.length) {
    list.innerHTML = '<li><span style="color:var(--text2)">Aucune activité récente</span></li>';
    return;
  }
  list.innerHTML = activities.map(a => `
    <li>
      <span class="badge badge-${a.status}">${a.status}</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(a.filename)}</span>
      <span style="color:var(--text2)">${a.progress}%</span>
    </li>
  `).join('');
}

// ── CLIENTS ───────────────────────────────────────────────────
function renderClients(clients) {
  const tbody = document.getElementById('clients-tbody');
  if (!clients.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="no-data">Aucun client connecté</td></tr>';
    return;
  }
  tbody.innerHTML = clients.map(c => `
    <tr>
      <td style="font-family:monospace;font-size:12px">${escHtml(c.client_id_short)}</td>
      <td>${escHtml(c.ip_address)}</td>
      <td><span class="badge badge-${c.status}">${escHtml(c.status)}</span></td>
      <td>${c.active_batches}/${c.max_batches}</td>
      <td>${escHtml(c.last_heartbeat)}</td>
      <td>${escHtml(c.uptime)}</td>
      <td>
        <button class="btn btn-danger btn-sm" onclick="disconnectClient('${escHtml(c.client_id)}')">
          Déconnecter
        </button>
      </td>
    </tr>
  `).join('');
}

async function disconnectClient(clientId) {
  if (!confirm('Déconnecter ce client ?')) return;
  const res = await apiFetch(`/api/clients/${encodeURIComponent(clientId)}/disconnect`, { method: 'POST' });
  if (res && res.ok) showToast('Client déconnecté');
  else showToast('Erreur déconnexion', true);
}

// ── JOBS ──────────────────────────────────────────────────────
function renderJobs(jobs) {
  const tbody = document.getElementById('jobs-tbody');
  if (!jobs.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="no-data">Aucun job</td></tr>';
    return;
  }
  tbody.innerHTML = jobs.map(j => `
    <tr>
      <td style="font-family:monospace;font-size:12px">${escHtml(j.video_id_short)}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(j.filename)}">${escHtml(j.filename)}</td>
      <td><span class="badge badge-${j.status}">${escHtml(j.status)}</span></td>
      <td style="min-width:120px">
        <progress value="${j.progress}" max="100"></progress>
        <div style="font-size:11px;color:var(--text2);margin-top:2px">${j.progress}%</div>
      </td>
      <td>${j.completed_batches}/${j.total_batches}</td>
      <td>x${j.upscale_factor}</td>
      <td style="font-size:12px;max-width:120px;overflow:hidden;text-overflow:ellipsis" title="${escHtml(j.model)}">${escHtml(j.model)}</td>
      <td>${j.tta_mode ? '✓' : '—'}</td>
      <td>
        <button class="btn btn-danger btn-sm" onclick="deleteJob('${escHtml(j.video_id)}')"
          ${j.status === 'completed' || j.status === 'failed' ? '' : ''}>
          ${j.status === 'completed' || j.status === 'failed' ? 'Supprimer' : 'Annuler'}
        </button>
      </td>
    </tr>
  `).join('');
}

async function deleteJob(videoId) {
  if (!confirm('Annuler/supprimer ce job ?')) return;
  const res = await apiFetch(`/api/jobs/${encodeURIComponent(videoId)}`, { method: 'DELETE' });
  if (res && res.ok) showToast('Job supprimé');
  else showToast('Erreur suppression', true);
}

// ── ADD JOB MODAL ─────────────────────────────────────────────
function showAddJobModal() {
  document.getElementById('add-job-modal').style.display = 'flex';
  document.getElementById('job-path').focus();
}

function closeJobModal() {
  document.getElementById('add-job-modal').style.display = 'none';
  document.getElementById('job-error').style.display = 'none';
}

function updateJobModels() {
  const engine = document.getElementById('job-engine').value;
  const modelSel = document.getElementById('job-model');
  const denoiseGrp = document.getElementById('job-denoise-group');

  if (engine === 'realesrgan') {
    modelSel.innerHTML = `
      <option value="realesr-animevideov3">realesr-animevideov3 (recommandé)</option>
      <option value="realesrgan-x4plus-anime">realesrgan-x4plus-anime</option>
      <option value="realesrgan-x4plus">realesrgan-x4plus</option>`;
    denoiseGrp.style.display = 'none';
  } else {
    modelSel.innerHTML = `
      <option value="models-se">models-se (recommandé)</option>
      <option value="models-pro">models-pro</option>
      <option value="models-nose">models-nose</option>`;
    denoiseGrp.style.display = 'block';
  }
}

async function submitJob() {
  const errEl = document.getElementById('job-error');
  errEl.style.display = 'none';

  const body = {
    path: document.getElementById('job-path').value.trim(),
    upscale_factor: parseInt(document.getElementById('job-scale').value),
    engine: document.getElementById('job-engine').value,
    model: document.getElementById('job-model').value,
    tta_mode: document.getElementById('job-tta').checked,
    denoise_level: parseInt(document.getElementById('job-denoise')?.value ?? '-1')
  };

  if (!body.path) {
    errEl.textContent = 'Veuillez saisir un chemin de fichier.';
    errEl.style.display = 'block';
    return;
  }

  const res = await apiFetch('/api/jobs', {
    method: 'POST',
    body: JSON.stringify(body)
  });

  if (res && res.ok) {
    closeJobModal();
    showToast('Vidéo ajoutée à la queue');
  } else {
    const data = res ? await res.json().catch(() => ({})) : {};
    errEl.textContent = data.detail || 'Erreur lors de l\'ajout.';
    errEl.style.display = 'block';
  }
}

// ── CONFIGURATION ─────────────────────────────────────────────
async function loadConfig() {
  const res = await apiFetch('/api/config');
  if (!res || !res.ok) return;
  const cfg = await res.json();

  setVal('cfg-ipv4', cfg.ipv4 || '');
  setVal('cfg-ipv6', cfg.ipv6 || '');
  setVal('cfg-port', cfg.port || 8765);
  setVal('cfg-data-port', cfg.data_port || 8766);
  setVal('cfg-password', cfg.password || '');
  setVal('cfg-batch-size', cfg.batch_size || 100);
  setVal('cfg-max-batches', cfg.max_concurrent_batches || 3);
  setVal('cfg-compression', cfg.compression_level || 5);
  setVal('cfg-work-dir', cfg.work_directory || './work');
}

function scheduleConfigSave() {
  if (_configSaveTimeout) clearTimeout(_configSaveTimeout);
  _configSaveTimeout = setTimeout(saveConfig, 500);
}

async function saveConfig() {
  const params = {
    server_ipv4: getVal('cfg-ipv4'),
    server_ipv6: getVal('cfg-ipv6'),
    server_port: getVal('cfg-port'),
    server_data_port: getVal('cfg-data-port'),
    server_password: getVal('cfg-password'),
    batch_size: getVal('cfg-batch-size'),
    max_concurrent_batches: getVal('cfg-max-batches'),
    compression_level: getVal('cfg-compression'),
    work_directory: getVal('cfg-work-dir')
  };

  const res = await apiFetch('/api/config', {
    method: 'PUT',
    body: JSON.stringify({ params })
  });

  if (res && res.ok) {
    const ind = document.getElementById('save-indicator');
    ind.classList.add('show');
    setTimeout(() => ind.classList.remove('show'), 2000);
  }
}

// ── WEBHOOKS ──────────────────────────────────────────────────
async function loadWebhooks() {
  const res = await apiFetch('/api/webhooks');
  if (!res || !res.ok) return;
  const wh = await res.json();
  document.getElementById('wh-enabled').checked = wh.enabled || false;
  setVal('wh-url', wh.url || '');
}

function scheduleWebhookSave() {
  if (_webhookSaveTimeout) clearTimeout(_webhookSaveTimeout);
  _webhookSaveTimeout = setTimeout(saveWebhooks, 500);
}

async function saveWebhooks() {
  const body = {
    enabled: document.getElementById('wh-enabled').checked,
    url: getVal('wh-url'),
    events: ''
  };
  await apiFetch('/api/webhooks', { method: 'PUT', body: JSON.stringify(body) });
}

async function testWebhook() {
  const res = await apiFetch('/api/webhooks/test', { method: 'POST' });
  const resultEl = document.getElementById('wh-test-result');
  if (res && res.ok) {
    const data = await res.json();
    resultEl.style.color = data.success ? 'var(--success)' : 'var(--danger)';
    resultEl.textContent = data.success ? '✓ Webhook envoyé' : `✗ ${data.error || 'Erreur'}`;
  } else {
    resultEl.style.color = 'var(--danger)';
    resultEl.textContent = '✗ Erreur réseau';
  }
  setTimeout(() => { resultEl.textContent = ''; }, 4000);
}

// ── TAB NAVIGATION ────────────────────────────────────────────
function switchTab(name, btn) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  localStorage.setItem('server_web_tab', name);
}

function restoreTab() {
  const tab = localStorage.getItem('server_web_tab');
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
  // Simple toast notification
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:24px;right:24px;padding:10px 18px;border-radius:6px;
    background:${error ? 'var(--danger)' : 'var(--success)'};color:#fff;font-size:13px;
    font-weight:600;z-index:9999;box-shadow:var(--shadow);animation:fadeIn .3s;`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}
