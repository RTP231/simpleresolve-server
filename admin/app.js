'use strict';

// ── Config ─────────────────────────────────────────────────────────────────
const API_BASE = 'https://simpleresolve-server-production.up.railway.app';

// ── Estado ─────────────────────────────────────────────────────────────────
let _step1Token   = null;
let _adminToken   = null;
let _users        = [];
let _filtered     = [];
let _activeFilter = 'all';
let _searchQuery  = '';
let _editingId    = null;
let _deletingId   = null;
let _detailUserId = null;
let _detailData   = null;
let _toastTimer   = null;
let _chart        = null;

// ── Helpers DOM ────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => {
    s.classList.toggle('active', s.id === `screen-${name}`);
    s.classList.toggle('hidden', s.id !== `screen-${name}`);
  });
}

function showModal(id) { $(id).classList.remove('hidden'); }
function closeModal(id) { $(id).classList.add('hidden'); }
function overlayClose(e, id) { if (e.target.id === id) closeModal(id); }

function showError(id, msg) { const el = $(id); el.textContent = msg; el.classList.remove('hidden'); }
function clearError(id)     { $(id).classList.add('hidden'); }

function toast(msg, type = 'success') {
  const el = $('toast');
  el.textContent = msg;
  el.className = `toast toast-${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add('hidden'), 3200);
}

function btnLoading(btn, loading, label) {
  btn.disabled    = loading;
  btn.textContent = loading ? '…' : label;
}

async function apiFetch(path, opts = {}) {
  const url     = `${API_BASE}${path}`;
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (_adminToken) headers['Authorization'] = `Bearer ${_adminToken}`;
  const res  = await fetch(url, { ...opts, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw { status: res.status, detail: body.detail || `Error ${res.status}` };
  return body;
}

// ── Fecha / tiempo ─────────────────────────────────────────────────────────
function daysUntil(isoStr) {
  if (!isoStr) return null;
  return Math.ceil((new Date(isoStr) - Date.now()) / 86400000);
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  return new Date(isoStr).toLocaleDateString('es-ES', { day:'numeric', month:'short', year:'numeric' });
}

function formatDateTime(isoStr) {
  if (!isoStr) return '—';
  const d = new Date(isoStr);
  return d.toLocaleDateString('es-ES', { day:'2-digit', month:'short' })
    + ' ' + d.toLocaleTimeString('es-ES', { hour:'2-digit', minute:'2-digit' });
}

function timeAgo(isoStr) {
  if (!isoStr) return 'Nunca';
  const mins = Math.floor((Date.now() - new Date(isoStr)) / 60000);
  if (mins < 1)   return 'Hace un momento';
  if (mins < 60)  return `Hace ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)   return `Hace ${hrs}h`;
  return `Hace ${Math.floor(hrs / 24)}d`;
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Expiry cell HTML ───────────────────────────────────────────────────────
function expiryHTML(isoStr) {
  const days    = daysUntil(isoStr);
  const dateStr = formatDate(isoStr);
  if (days === null) return `<span class="expiry-muted">Sin límite</span>`;
  if (days < 0)   return `<span class="expiry-danger">${dateStr}<span class="expiry-sub">Vencida hace ${Math.abs(days)}d</span></span>`;
  if (days <= 7)  return `<span class="expiry-warn">${dateStr}<span class="expiry-sub">⚠ Vence en ${days}d</span></span>`;
  return `<span class="expiry-ok">${dateStr}<span class="expiry-sub expiry-muted">${days}d restantes</span></span>`;
}

// ── Status badge ───────────────────────────────────────────────────────────
function statusBadge(user) {
  if (!user.activo) return '<span class="badge badge-blocked">■ Suspendido</span>';
  const days = daysUntil(user.fecha_vencimiento);
  if (days !== null && days < 0) return '<span class="badge badge-expired">✕ Vencida</span>';
  if (user.last_seen && (Date.now() - new Date(user.last_seen)) / 60000 < 5)
    return '<span class="badge badge-online">◉ Activo ahora</span>';
  if (days !== null && days <= 7) return '<span class="badge badge-warning">⚠ Por vencer</span>';
  return '<span class="badge badge-active">● Activo</span>';
}

// ── Capturas usadas ────────────────────────────────────────────────────────
function capturesUsedText(user) {
  const limite = user.captures_limite ?? null;
  const rem    = user.captures_remaining ?? 0;
  if (limite === null) return `<span class="cap-text">${rem} restantes</span>`;
  const used = Math.max(0, limite - rem);
  return `<span class="cap-text">${used} / ${limite}</span>`;
}

// ══════════════════════════════════════════════════════════════
//  LOGIN
// ══════════════════════════════════════════════════════════════
$('btn-password').addEventListener('click', submitPassword);
$('inp-password').addEventListener('keydown', e => e.key === 'Enter' && submitPassword());

async function submitPassword() {
  const password = $('inp-password').value;
  if (!password) { showError('err-password', 'Ingresa la contraseña.'); return; }
  clearError('err-password');
  btnLoading($('btn-password'), true, 'Continuar →');
  try {
    const data = await apiFetch('/admin/auth/password', { method:'POST', body:JSON.stringify({ password }) });
    _step1Token = data.step1_token;
    if (data.totp_setup) {
      $('qr-img').src = `data:image/png;base64,${data.qr_image}`;
      $('totp-secret-text').textContent = data.totp_secret;
      $('qr-setup').classList.remove('hidden');
    } else {
      $('qr-setup').classList.add('hidden');
    }
    $('step-password').classList.add('hidden');
    $('step-totp').classList.remove('hidden');
    $('inp-totp').value = ''; $('inp-totp').focus();
  } catch (err) {
    showError('err-password', err.detail || 'Error de conexión.');
  } finally {
    btnLoading($('btn-password'), false, 'Continuar →');
  }
}

$('btn-totp').addEventListener('click', submitTotp);
$('inp-totp').addEventListener('keydown', e => e.key === 'Enter' && submitTotp());
$('inp-totp').addEventListener('input', function () {
  let val = this.value.replace(/\D/g,'').slice(0,6);
  if (val.length > 3) val = val.slice(0,3) + ' ' + val.slice(3);
  this.value = val;
});
$('btn-back').addEventListener('click', () => {
  $('step-totp').classList.add('hidden');
  $('step-password').classList.remove('hidden');
  clearError('err-totp');
  _step1Token = null;
});

async function submitTotp() {
  const code = $('inp-totp').value.replace(/\s/g,'');
  if (code.length !== 6) { showError('err-totp', 'El código debe tener 6 dígitos.'); return; }
  clearError('err-totp');
  btnLoading($('btn-totp'), true, 'Verificando…');
  try {
    const data = await apiFetch('/admin/auth/totp', {
      method:'POST', headers:{ Authorization:`Bearer ${_step1Token}` },
      body:JSON.stringify({ code }),
    });
    _adminToken = data.access_token;
    showScreen('dashboard');
    loadDashboard();
  } catch (err) {
    showError('err-totp', err.detail || 'Código incorrecto.');
  } finally {
    btnLoading($('btn-totp'), false, 'Iniciar sesión');
  }
}

// ── Logout ─────────────────────────────────────────────────────────────────
$('btn-logout').addEventListener('click', () => {
  _adminToken = null; _step1Token = null; _users = []; _filtered = [];
  if (_chart) { _chart.destroy(); _chart = null; }
  $('inp-password').value = ''; $('inp-totp').value = '';
  $('step-password').classList.remove('hidden'); $('step-totp').classList.add('hidden');
  clearError('err-password'); clearError('err-totp');
  showScreen('login');
});

// ══════════════════════════════════════════════════════════════
//  DASHBOARD
// ══════════════════════════════════════════════════════════════
async function loadDashboard() {
  await Promise.all([loadUsers(), loadStats()]);
}


async function loadStats() {
  try {
    const s = await apiFetch('/admin/stats');

    // Revenue
    $('stat-revenue').textContent = s.price > 0
      ? `$${s.revenue.toLocaleString('es-ES', { minimumFractionDigits:2, maximumFractionDigits:2 })}`
      : '—';
    $('inp-price').value = s.price > 0 ? s.price : '';

    // 24h
    $('act-opens').textContent = s.activity_24h.opens;
    $('act-caps').textContent  = s.activity_24h.captures;
    $('act-users').textContent = s.activity_24h.unique_users;

    // Chart
    renderChart(s.chart);
  } catch {
    // stats falla silenciosamente; la tabla sigue funcionando
  }
}

function renderChart(data) {
  const ctx = $('chart-captures').getContext('2d');
  if (_chart) _chart.destroy();

  const labels = data.map(d => {
    const dt = new Date(d.date + 'T12:00:00');
    return dt.toLocaleDateString('es-ES', { weekday:'short', day:'numeric' });
  });
  const values = data.map(d => d.count);

  _chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Capturas',
        data: values,
        backgroundColor: 'rgba(124,111,255,0.55)',
        borderColor:     'rgba(124,111,255,0.9)',
        borderWidth: 1,
        borderRadius: 5,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend:{ display:false }, tooltip:{ callbacks:{
        label: ctx => ` ${ctx.parsed.y} captura${ctx.parsed.y !== 1 ? 's' : ''}`,
      }}},
      scales: {
        x: { grid:{ color:'rgba(255,255,255,0.04)' }, ticks:{ color:'#55547a', font:{ size:11 } } },
        y: { grid:{ color:'rgba(255,255,255,0.04)' }, ticks:{ color:'#55547a', font:{ size:11 }, stepSize:1, precision:0 }, beginAtZero:true },
      },
    },
  });
}

// ── Price config ───────────────────────────────────────────────────────────
$('btn-price-toggle').addEventListener('click', () => {
  $('price-panel').classList.toggle('hidden');
});

$('btn-save-price').addEventListener('click', async () => {
  const price = parseFloat($('inp-price').value);
  if (isNaN(price) || price < 0) { toast('Precio inválido.', 'error'); return; }
  const btn = $('btn-save-price');
  btnLoading(btn, true, 'Guardar');
  try {
    await apiFetch('/admin/config/price', { method:'POST', body:JSON.stringify({ price }) });
    toast('Precio guardado.');
    $('price-panel').classList.add('hidden');
    loadStats();
  } catch (err) {
    toast(err.detail || 'Error al guardar.', 'error');
  } finally {
    btnLoading(btn, false, 'Guardar');
  }
});

// ══════════════════════════════════════════════════════════════
//  USUARIOS
// ══════════════════════════════════════════════════════════════
async function loadUsers() {
  $('users-tbody').innerHTML = '<tr><td colspan="6" class="loading-row">Cargando…</td></tr>';
  try {
    _users = await apiFetch('/admin/users');
    applyFilterAndSearch();
    renderStats();
  } catch (err) {
    $('users-tbody').innerHTML = `<tr><td colspan="6" class="loading-row" style="color:var(--danger)">Error: ${escHtml(err.detail)}</td></tr>`;
  }
}

// ── Stats cards ────────────────────────────────────────────────────────────
function renderStats() {
  let active = 0, expiring = 0, problem = 0;
  _users.forEach(u => {
    if (!u.activo) { problem++; return; }
    const days = daysUntil(u.fecha_vencimiento);
    if (days !== null && days < 0) { problem++; }
    else if (days !== null && days <= 7) { expiring++; active++; }
    else { active++; }
  });
  $('stat-total').textContent    = _users.length;
  $('stat-active').textContent   = active;
  $('stat-expiring').textContent = expiring;
  $('stat-expired').textContent  = problem;
}

// ── Filtros y búsqueda ─────────────────────────────────────────────────────
document.querySelectorAll('.filter-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    _activeFilter = btn.dataset.filter;
    applyFilterAndSearch();
  });
});

$('inp-search').addEventListener('input', function () {
  _searchQuery = this.value.toLowerCase().trim();
  applyFilterAndSearch();
});

function applyFilterAndSearch() {
  let list = [..._users];

  // Filter
  if (_activeFilter !== 'all') {
    list = list.filter(u => {
      const days = daysUntil(u.fecha_vencimiento);
      switch (_activeFilter) {
        case 'active':    return u.activo && (days === null || days >= 0);
        case 'expiring':  return u.activo && days !== null && days >= 0 && days <= 7;
        case 'expired':   return days !== null && days < 0;
        case 'suspended': return !u.activo;
        default: return true;
      }
    });
  }

  // Search
  if (_searchQuery) {
    list = list.filter(u => u.email.toLowerCase().includes(_searchQuery));
  }

  _filtered = list;
  renderUsers();
}

function renderUsers() {
  if (!_filtered.length) {
    $('users-tbody').innerHTML = '<tr><td colspan="6" class="empty-row">No hay usuarios que coincidan.</td></tr>';
    return;
  }
  $('users-tbody').innerHTML = _filtered.map(u => `
    <tr onclick="openDetail('${u.id}')" title="Ver detalle">
      <td class="col-email"><span class="email-text">${escHtml(u.email)}</span></td>
      <td>${capturesUsedText(u)}</td>
      <td><span class="last-seen-text">${timeAgo(u.last_seen)}</span></td>
      <td>${expiryHTML(u.fecha_vencimiento)}</td>
      <td>${statusBadge(u)}</td>
      <td class="col-actions" onclick="event.stopPropagation()">
        <div class="actions-cell">
          <button class="btn-icon" title="Editar" onclick="openEdit('${u.id}')">✎</button>
          <button class="btn-icon ${u.activo ? 'warn' : 'ok'}" title="${u.activo ? 'Suspender' : 'Activar'}" onclick="quickToggle('${u.id}')">
            ${u.activo ? '⊘' : '▶'}
          </button>
          <button class="btn-icon danger" title="Eliminar" onclick="openDelete('${u.id}','${escHtml(u.email)}')">🗑</button>
        </div>
      </td>
    </tr>
  `).join('');
}

async function quickToggle(id) {
  const user = _users.find(u => u.id === id);
  if (!user) return;
  try {
    await apiFetch(`/admin/users/${id}`, { method:'PATCH', body:JSON.stringify({ activo: !user.activo }) });
    toast(user.activo ? 'Cuenta suspendida.' : 'Cuenta activada.');
    await loadUsers();
  } catch (err) { toast(err.detail || 'Error.', 'error'); }
}

// ══════════════════════════════════════════════════════════════
//  MODAL DETALLE
// ══════════════════════════════════════════════════════════════
function openDetail(id) {
  _detailUserId = id;
  _detailData   = null;
  const user = _users.find(u => u.id === id);
  if (!user) return;

  $('detail-email').textContent      = user.email;
  $('detail-status-badge').innerHTML = statusBadge(user);
  $('detail-created').textContent    = formatDate(user.created_at);
  $('detail-last-seen').textContent  = timeAgo(user.last_seen);
  $('detail-total-used').textContent = '…';
  $('detail-today-used').textContent = '…';
  $('detail-notes').value            = '';
  $('detail-failed-count').textContent = 'Intentos fallidos: …';
  $('detail-ip-anomaly').classList.add('hidden');
  $('login-log-tbody').innerHTML     = '<tr><td colspan="3" class="loading-row">…</td></tr>';
  $('detail-timeline').innerHTML     = '<p class="empty-row" style="padding:10px">Cargando…</p>';

  const btn = $('btn-detail-suspend');
  btn.textContent = user.activo ? 'Suspender' : 'Activar';
  btn.className   = user.activo ? 'btn btn-danger btn-sm' : 'btn btn-primary btn-sm';

  showModal('modal-detail');
  fetchDetail(id);
}

async function fetchDetail(id) {
  try {
    const data = await apiFetch(`/admin/users/${id}/details`);
    _detailData = data;
    const user  = data.user;

    $('detail-total-used').textContent = data.captures_used_total;
    $('detail-today-used').textContent = data.captures_used_today;
    $('detail-notes').value            = user.notes || '';
    $('detail-failed-count').textContent = `Intentos fallidos: ${data.failed_count}`;

    if (data.ip_anomaly) $('detail-ip-anomaly').classList.remove('hidden');

    // Login logs
    const logs = data.login_logs || [];
    if (!logs.length) {
      $('login-log-tbody').innerHTML = '<tr><td colspan="3" class="empty-row">Sin registros.</td></tr>';
    } else {
      $('login-log-tbody').innerHTML = logs.map(l => {
        const dt = new Date(l.logged_at);
        return `<tr>
          <td>${dt.toLocaleDateString('es-ES',{day:'2-digit',month:'short',year:'numeric'})}</td>
          <td>${dt.toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}</td>
          <td><code class="ip-code">${escHtml(l.ip)}</code></td>
        </tr>`;
      }).join('');
    }

    // Timeline
    const tl = data.timeline || [];
    if (!tl.length) {
      $('detail-timeline').innerHTML = '<p class="empty-row" style="padding:10px">Sin actividad registrada.</p>';
    } else {
      const icons = { app_open:'🚀', capture:'📸', app_close:'🔴' };
      $('detail-timeline').innerHTML = tl.map(e => `
        <div class="timeline-item">
          <span class="tl-icon">${icons[e.event_type] || '•'}</span>
          <span class="tl-event">${escHtml(e.event_type.replace(/_/g,' '))}</span>
          <span class="tl-time">${formatDateTime(e.timestamp)}</span>
          <code class="tl-ip">${escHtml(e.ip || '—')}</code>
          <span class="tl-ver">${escHtml(e.app_version || '')}</span>
        </div>
      `).join('');
    }
  } catch (err) {
    $('detail-timeline').innerHTML = `<p class="empty-row" style="color:var(--danger);padding:10px">${escHtml(err.detail || String(err))}</p>`;
  }
}

function openEditFromDetail() {
  closeModal('modal-detail');
  openEdit(_detailUserId);
}

// ── Notas ──────────────────────────────────────────────────────────────────
async function saveNotes() {
  if (!_detailUserId) return;
  const notes = $('detail-notes').value;
  const btn   = $('btn-save-notes');
  btnLoading(btn, true, 'Guardar notas');
  try {
    await apiFetch(`/admin/users/${_detailUserId}/notes`, { method:'PATCH', body:JSON.stringify({ notes }) });
    toast('Notas guardadas.');
  } catch (err) {
    toast(err.detail || 'Error al guardar.', 'error');
  } finally {
    btnLoading(btn, false, 'Guardar notas');
  }
}

// ── Suspender / Activar ────────────────────────────────────────────────────
async function toggleSuspend() {
  if (!_detailUserId) return;
  const user = _users.find(u => u.id === _detailUserId);
  if (!user) return;
  const newActivo = !user.activo;
  const btn       = $('btn-detail-suspend');
  btnLoading(btn, true, '…');
  try {
    await apiFetch(`/admin/users/${_detailUserId}`, { method:'PATCH', body:JSON.stringify({ activo: newActivo }) });
    toast(newActivo ? 'Cuenta activada.' : 'Cuenta suspendida.');
    await loadUsers();
    const updated = _users.find(u => u.id === _detailUserId);
    if (updated) {
      $('detail-status-badge').innerHTML = statusBadge(updated);
      btn.textContent = updated.activo ? 'Suspender' : 'Activar';
      btn.className   = updated.activo ? 'btn btn-danger btn-sm' : 'btn btn-primary btn-sm';
    }
  } catch (err) {
    toast(err.detail || 'Error.', 'error');
  } finally { btn.disabled = false; }
}

// ── Fuerza-logout ──────────────────────────────────────────────────────────
async function forceLogout() {
  if (!_detailUserId) return;
  if (!confirm('¿Invalidar la sesión activa? El usuario será desconectado en máximo 3 minutos.')) return;
  const btn = $('btn-force-logout');
  btnLoading(btn, true, '⊘ Cerrar sesión');
  try {
    await apiFetch(`/admin/users/${_detailUserId}/force-logout`, { method:'POST' });
    toast('Sesión invalidada. Se cerrará en máximo 3 min.', 'warn');
  } catch (err) {
    toast(err.detail || 'Error.', 'error');
  } finally {
    btnLoading(btn, false, '⊘ Cerrar sesión');
  }
}

// ── Export PDF ─────────────────────────────────────────────────────────────
function exportPDF() {
  if (!_detailData) { toast('Cargando datos…', 'warn'); return; }
  const { jsPDF } = window.jspdf;
  const doc  = new jsPDF();
  const user = _detailData.user;
  const tl   = _detailData.timeline   || [];
  const logs = _detailData.login_logs || [];

  // Header
  doc.setFontSize(16); doc.setFont('helvetica','bold');
  doc.setTextColor(124,111,255);
  doc.text('SimpleResolve — Registro de actividad', 20, 20);
  doc.setDrawColor(124,111,255); doc.setLineWidth(0.5);
  doc.line(20, 24, 190, 24);

  // User info
  doc.setFontSize(11); doc.setFont('helvetica','normal'); doc.setTextColor(30,30,50);
  doc.text(`Usuario: ${user.email}`,           20, 34);
  doc.text(`Registrado: ${formatDate(user.created_at)}`, 20, 41);
  doc.text(`Estado: ${user.activo ? 'Activo' : 'Suspendido'}`, 20, 48);
  doc.text(`Capturas usadas: ${_detailData.captures_used_total} / ${user.captures_limite ?? '∞'}`, 20, 55);
  doc.text(`Última actividad: ${formatDateTime(user.last_seen)}`, 20, 62);

  let y = 72;

  // Timeline
  doc.setFontSize(12); doc.setFont('helvetica','bold'); doc.setTextColor(50,50,80);
  doc.text('Timeline de actividad', 20, y); y += 2;

  doc.autoTable({
    startY: y,
    head: [['Fecha', 'Hora', 'Evento', 'IP', 'Versión']],
    body: tl.map(e => {
      const dt = new Date(e.timestamp);
      return [
        dt.toLocaleDateString('es-ES'),
        dt.toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit',second:'2-digit'}),
        e.event_type.replace(/_/g,' '),
        e.ip || '—',
        e.app_version || '—',
      ];
    }),
    styles: { fontSize:9, cellPadding:3 },
    headStyles: { fillColor:[124,111,255], textColor:255, fontStyle:'bold' },
    alternateRowStyles: { fillColor:[245,244,255] },
    margin: { left:20, right:20 },
  });

  y = doc.lastAutoTable.finalY + 12;

  // Login history
  doc.setFontSize(12); doc.setFont('helvetica','bold'); doc.setTextColor(50,50,80);
  doc.text('Historial de inicios de sesión', 20, y); y += 2;

  doc.autoTable({
    startY: y,
    head: [['Fecha', 'Hora', 'IP']],
    body: logs.map(l => {
      const dt = new Date(l.logged_at);
      return [
        dt.toLocaleDateString('es-ES'),
        dt.toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit',second:'2-digit'}),
        l.ip,
      ];
    }),
    styles: { fontSize:9, cellPadding:3 },
    headStyles: { fillColor:[0,180,140], textColor:255, fontStyle:'bold' },
    alternateRowStyles: { fillColor:[240,255,252] },
    margin: { left:20, right:20 },
  });

  // Footer signature
  const finalY = doc.lastAutoTable.finalY + 14;
  doc.setFontSize(9); doc.setFont('helvetica','italic'); doc.setTextColor(120,120,150);
  doc.text(`Generado el ${new Date().toLocaleString('es-ES')} por SimpleResolve Admin`, 20, finalY);
  doc.text('Este documento certifica el registro de uso de la plataforma SimpleResolve.', 20, finalY + 6);

  doc.save(`SR_${user.email}_${new Date().toISOString().slice(0,10)}.pdf`);
}

// ══════════════════════════════════════════════════════════════
//  MODAL CREAR / EDITAR
// ══════════════════════════════════════════════════════════════
$('btn-new-user').addEventListener('click', openCreate);

function openCreate() {
  _editingId = null;
  $('modal-title').textContent = 'Nuevo usuario';
  $('create-fields').classList.remove('hidden');
  $('remaining-col').classList.add('hidden');
  $('active-field').classList.add('hidden');
  $('days-label').textContent = 'Días de acceso';
  $('days-hint').classList.add('hidden');
  $('f-email').value = ''; $('f-password').value = '';
  $('f-limite').value = '200'; $('f-days').value = '30';
  $('f-active').checked = true;
  clearError('modal-error');
  showModal('modal-user');
  $('f-email').focus();
}

function openEdit(id) {
  const user = _users.find(u => u.id === id);
  if (!user) return;
  _editingId = id;

  $('modal-title').textContent = 'Editar usuario';
  $('create-fields').classList.add('hidden');
  $('remaining-col').classList.remove('hidden');
  $('active-field').classList.remove('hidden');

  $('f-limite').value    = user.captures_limite ?? user.captures_remaining ?? '';
  $('f-remaining').value = user.captures_remaining ?? '';
  $('f-active').checked  = user.activo !== false;
  $('f-days').value      = '';
  $('days-label').textContent = 'Días a extender vencimiento';

  const days = daysUntil(user.fecha_vencimiento);
  if (days !== null) {
    const hint = days >= 0
      ? `Vence en ${days}d (${formatDate(user.fecha_vencimiento)}). Vacío = sin cambio.`
      : `Vencida hace ${Math.abs(days)}d. Vacío = sin cambio.`;
    $('days-hint').textContent = hint;
    $('days-hint').classList.remove('hidden');
  } else {
    $('days-hint').classList.add('hidden');
  }

  clearError('modal-error');
  showModal('modal-user');
  $('f-limite').focus();
}

$('btn-modal-save').addEventListener('click', saveUser);

async function saveUser() {
  clearError('modal-error');
  const btn = $('btn-modal-save');
  btnLoading(btn, true, 'Guardar');
  try {
    if (_editingId === null) await createUser();
    else await editUser(_editingId);
    closeModal('modal-user');
    await loadUsers();
    toast(_editingId === null ? 'Usuario creado.' : 'Usuario actualizado.');
  } catch (err) {
    showError('modal-error', err.detail || String(err));
  } finally {
    btnLoading(btn, false, 'Guardar');
  }
}

async function createUser() {
  const email    = $('f-email').value.trim();
  const password = $('f-password').value;
  const limite   = parseInt($('f-limite').value);
  const dias     = parseInt($('f-days').value);
  if (!email)                          throw { detail:'El email es obligatorio.' };
  if (!password)                       throw { detail:'La contraseña es obligatoria.' };
  if (password.length < 8)            throw { detail:'La contraseña debe tener al menos 8 caracteres.' };
  if (isNaN(limite) || limite < 0)    throw { detail:'Límite de capturas inválido.' };
  if (isNaN(dias)   || dias < 1)      throw { detail:'Los días de acceso deben ser al menos 1.' };
  return apiFetch('/admin/users', { method:'POST', body:JSON.stringify({ email, password, captures_limite:limite, dias_acceso:dias }) });
}

async function editUser(id) {
  const body     = {};
  const limite   = $('f-limite').value.trim();
  const remaining= $('f-remaining').value.trim();
  const dias     = $('f-days').value.trim();
  const activo   = $('f-active').checked;
  if (limite    !== '') body.captures_limite    = parseInt(limite);
  if (remaining !== '') body.captures_remaining = parseInt(remaining);
  if (dias      !== '') body.dias_acceso        = parseInt(dias);
  const user = _users.find(u => u.id === id);
  if (user && user.activo !== activo) body.activo = activo;
  if (!Object.keys(body).length) throw { detail:'No hay cambios que guardar.' };
  if ('captures_limite'    in body && isNaN(body.captures_limite))    throw { detail:'Límite inválido.' };
  if ('captures_remaining' in body && isNaN(body.captures_remaining)) throw { detail:'Restantes inválido.' };
  if ('dias_acceso'        in body && (isNaN(body.dias_acceso) || body.dias_acceso < 1)) throw { detail:'Días inválidos.' };
  return apiFetch(`/admin/users/${id}`, { method:'PATCH', body:JSON.stringify(body) });
}

// ══════════════════════════════════════════════════════════════
//  MODAL ELIMINAR
// ══════════════════════════════════════════════════════════════
function openDelete(id, email) {
  _deletingId = id;
  $('delete-email').textContent = email;
  showModal('modal-delete');
}

$('btn-confirm-delete').addEventListener('click', async () => {
  if (!_deletingId) return;
  const btn = $('btn-confirm-delete');
  btnLoading(btn, true, 'Eliminando…');
  try {
    await apiFetch(`/admin/users/${_deletingId}`, { method:'DELETE' });
    closeModal('modal-delete');
    await loadUsers();
    toast('Usuario eliminado.');
  } catch (err) {
    toast(err.detail || 'Error al eliminar.', 'error');
  } finally {
    btnLoading(btn, false, 'Eliminar');
    _deletingId = null;
  }
});

// ── Enter en modales ───────────────────────────────────────────────────────
['f-email','f-password','f-limite','f-remaining','f-days'].forEach(id => {
  const el = $(id);
  if (el) el.addEventListener('keydown', e => e.key === 'Enter' && saveUser());
});

// ── TOTP copiar secret ─────────────────────────────────────────────────────
function copySecret() {
  navigator.clipboard.writeText($('totp-secret-text').textContent)
    .then(() => toast('Secreto copiado.'));
}

// ── Init ───────────────────────────────────────────────────────────────────
showScreen('login');
$('inp-password').focus();
