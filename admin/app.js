'use strict';

// ── Configuración ─────────────────────────────────────────────────────────────
const API_BASE = 'https://simpleresolve-server-production.up.railway.app';

// ── Estado ────────────────────────────────────────────────────────────────────
let _step1Token   = null;
let _adminToken   = null;

// ── Persistencia de sesión (6 horas) ─────────────────────────────────────────
const _TOKEN_KEY = 'sr_admin_token';
const _TOKEN_EXP = 'sr_admin_exp';
const _TOKEN_TTL = 6 * 60 * 60 * 1000; // 6 horas en ms

function _saveToken(token) {
  localStorage.setItem(_TOKEN_KEY, token);
  localStorage.setItem(_TOKEN_EXP, Date.now() + _TOKEN_TTL);
}

function _loadSavedToken() {
  const token = localStorage.getItem(_TOKEN_KEY);
  const exp   = parseInt(localStorage.getItem(_TOKEN_EXP) || '0', 10);
  if (token && Date.now() < exp) return token;
  localStorage.removeItem(_TOKEN_KEY);
  localStorage.removeItem(_TOKEN_EXP);
  return null;
}

function _clearSavedToken() {
  localStorage.removeItem(_TOKEN_KEY);
  localStorage.removeItem(_TOKEN_EXP);
}
let _users        = [];
let _editingId    = null;
let _deletingId   = null;
let _welcomingId  = null;
let _reloadingId  = null;
let _genEmail      = '';
let _genPassword   = '';
let _historyUserId = null;
let _toastTimer    = null;

// ── Utilidades ────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => {
    s.classList.toggle('active',  s.id === `screen-${name}`);
    s.classList.toggle('hidden', s.id !== `screen-${name}`);
  });
}

function showModal(id) { $(id).classList.remove('hidden'); }
function closeModal(id) { $(id).classList.add('hidden'); }

function overlayClose(e, id) {
  if (e.target.id === id) closeModal(id);
}

function showError(id, msg) {
  const el = $(id);
  el.textContent = msg;
  el.classList.remove('hidden');
}

function clearError(id) { $(id).classList.add('hidden'); }

function toast(msg, type = 'success') {
  const el = $('toast');
  el.textContent = msg;
  el.className = `toast toast-${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add('hidden'), 3200);
}

function btnLoading(btn, loading, label) {
  btn.disabled = loading;
  btn.textContent = loading ? 'Cargando…' : label;
}

async function apiFetch(path, opts = {}) {
  const url = `${API_BASE}${path}`;
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (_adminToken) headers['Authorization'] = `Bearer ${_adminToken}`;
  const res = await fetch(url, { ...opts, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw { status: res.status, detail: body.detail || `Error ${res.status}` };
  return body;
}

// ── Helpers de fecha ──────────────────────────────────────────────────────────
function daysUntil(isoStr) {
  if (!isoStr) return null;
  const diff = new Date(isoStr) - Date.now();
  return Math.ceil(diff / 86400000);
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  return new Date(isoStr).toLocaleDateString('es-ES', {
    day: 'numeric', month: 'short', year: 'numeric'
  });
}

function expiryHTML(isoStr) {
  const days = daysUntil(isoStr);
  if (days === null) return '<span class="expiry-date">Sin límite</span>';
  const dateStr = formatDate(isoStr);
  if (days < 0) {
    return `<span class="expiry-date">${dateStr}</span>
            <span class="expiry-days expired">Vencida hace ${Math.abs(days)}d</span>`;
  }
  if (days <= 5) {
    return `<span class="expiry-date">${dateStr}</span>
            <span class="expiry-days warning">⚠ Vence en ${days}d</span>`;
  }
  return `<span class="expiry-date">${dateStr}</span>
          <span class="expiry-days ok">${days} días restantes</span>`;
}

function statusBadge(user) {
  if (!user.activo) {
    return '<span class="badge badge-blocked">■ Bloqueado</span>';
  }
  const days = daysUntil(user.fecha_vencimiento);
  if (days !== null && days < 0) {
    return '<span class="badge badge-expired">✕ Vencida</span>';
  }
  if (days !== null && days <= 5) {
    return '<span class="badge badge-warning">⚠ Por vencer</span>';
  }
  return '<span class="badge badge-active">● Activo</span>';
}

function capturesText(user) {
  const rem   = user.captures_remaining ?? '—';
  const limit = user.captures_limite ?? null;
  return limit !== null ? `${rem} / ${limit}` : `${rem}`;
}

// ── Login: paso 1 ─────────────────────────────────────────────────────────────
$('btn-password').addEventListener('click', submitPassword);
$('inp-password').addEventListener('keydown', e => e.key === 'Enter' && submitPassword());

async function submitPassword() {
  const password = $('inp-password').value;
  if (!password) { showError('err-password', 'Ingresa la contraseña.'); return; }

  clearError('err-password');
  btnLoading($('btn-password'), true, 'Continuar →');

  try {
    const data = await apiFetch('/admin/auth/password', {
      method: 'POST',
      body: JSON.stringify({ password }),
    });

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
    $('inp-totp').value = '';
    $('inp-totp').focus();

  } catch (err) {
    showError('err-password', err.detail || 'Error de conexión.');
  } finally {
    btnLoading($('btn-password'), false, 'Continuar →');
  }
}

// ── Login: paso 2 ─────────────────────────────────────────────────────────────
$('btn-totp').addEventListener('click', submitTotp);
$('inp-totp').addEventListener('keydown', e => e.key === 'Enter' && submitTotp());
$('inp-totp').addEventListener('input', function () {
  // Formatear automáticamente "123456" → "123 456"
  let val = this.value.replace(/\D/g, '').slice(0, 6);
  if (val.length > 3) val = val.slice(0, 3) + ' ' + val.slice(3);
  this.value = val;
});

$('btn-back').addEventListener('click', () => {
  $('step-totp').classList.add('hidden');
  $('step-password').classList.remove('hidden');
  clearError('err-totp');
  _step1Token = null;
});

async function submitTotp() {
  const code = $('inp-totp').value.replace(/\s/g, '');
  if (code.length !== 6) { showError('err-totp', 'El código debe tener 6 dígitos.'); return; }

  clearError('err-totp');
  btnLoading($('btn-totp'), true, 'Verificando…');

  try {
    const data = await apiFetch('/admin/auth/totp', {
      method: 'POST',
      headers: { Authorization: `Bearer ${_step1Token}` },
      body: JSON.stringify({ code }),
    });

    _adminToken = data.access_token;
    _saveToken(_adminToken);
    showScreen('dashboard');
    loadUsers();

  } catch (err) {
    showError('err-totp', err.detail || 'Código incorrecto.');
  } finally {
    btnLoading($('btn-totp'), false, 'Iniciar sesión');
  }
}

// ── Logout ────────────────────────────────────────────────────────────────────
$('btn-logout').addEventListener('click', () => {
  _adminToken  = null;
  _step1Token  = null;
  _users       = [];
  _clearSavedToken();
  $('inp-password').value = '';
  $('inp-totp').value = '';
  $('step-password').classList.remove('hidden');
  $('step-totp').classList.add('hidden');
  clearError('err-password');
  clearError('err-totp');
  showScreen('login');
});

// ── Cargar usuarios ────────────────────────────────────────────────────────────
async function loadUsers() {
  $('users-tbody').innerHTML = '<tr><td colspan="5" class="loading-row">Cargando…</td></tr>';

  try {
    _users = await apiFetch('/admin/users');
    renderUsers();
    renderStats();
  } catch (err) {
    $('users-tbody').innerHTML = `<tr><td colspan="5" class="loading-row" style="color:var(--danger)">
      Error al cargar usuarios: ${err.detail}</td></tr>`;
  }
}

function renderStats() {
  const now = Date.now();
  let active = 0, expiring = 0, problem = 0;

  _users.forEach(u => {
    if (!u.activo) { problem++; return; }
    const days = daysUntil(u.fecha_vencimiento);
    if (days !== null && days < 0) { problem++; }
    else if (days !== null && days <= 5) { expiring++; active++; }
    else { active++; }
  });

  $('stat-total').textContent    = _users.length;
  $('stat-active').textContent   = active;
  $('stat-expiring').textContent = expiring;
  $('stat-expired').textContent  = problem;
}

function welcomeBadge(user) {
  const sentAt = user.last_email_at || user.welcome_sent_at;
  if (!sentAt) {
    return '<span class="email-badge email-pending">Sin emails</span>';
  }
  const dt = new Date(sentAt);
  const now = new Date();
  const isToday = dt.toDateString() === now.toDateString();
  const timeStr = dt.toLocaleTimeString('es-ES', {hour: '2-digit', minute: '2-digit'});
  const label = isToday
    ? `Hoy ${timeStr}`
    : dt.toLocaleDateString('es-ES', {day: 'numeric', month: 'short'}) + ` ${timeStr}`;
  return `<span class="email-badge email-sent" title="Último email enviado">✉ ${label}</span>`;
}

function renderUsers() {
  if (!_users.length) {
    $('users-tbody').innerHTML = '<tr><td colspan="5" class="empty-row">No hay usuarios registrados.</td></tr>';
    return;
  }

  $('users-tbody').innerHTML = _users.map(u => `
    <tr>
      <td class="col-email">
        <span class="email-text user-detail-link" onclick="openUserDetail('${u.id}')" title="Ver detalle">${escHtml(u.email)}</span>
        ${welcomeBadge(u)}
      </td>
      <td><span class="captures-text">${capturesText(u)}</span></td>
      <td>${expiryHTML(u.fecha_vencimiento)}</td>
      <td>${statusBadge(u)}</td>
      <td class="col-actions">
        <div class="actions-cell">
          <button class="btn-icon" title="Editar" onclick="openEdit('${u.id}')">✎</button>
          <button class="btn-icon" title="Enviar bienvenida" onclick="openWelcome('${u.id}')">✉</button>
          <button class="btn-icon btn-icon-success" title="Recargar capturas" onclick="openReload('${u.id}')">⚡</button>
          <button class="btn-icon" title="Historial de comunicaciones" onclick="openEmailHistory('${u.id}','${escHtml(u.email)}')">📋</button>
          <button class="btn-icon danger" title="Eliminar" onclick="openDelete('${u.id}','${escHtml(u.email)}')">🗑</button>
        </div>
      </td>
    </tr>
  `).join('');
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Modal: crear usuario (nuevo flujo 3 pasos) ────────────────────────────────
$('btn-new-user').addEventListener('click', openCreate);

function openCreate() {
  _genEmail = _genPassword = '';
  $('f-dest-email').value    = '';
  $('f-dest-days').value     = '30';
  $('f-dest-captures').value = '200';
  clearError('cs-error-1');
  clearError('cs-error-2');
  showCreateStep(1);
  showModal('modal-create');
  $('f-dest-email').focus();
}

function showCreateStep(n) {
  [1, 2, 3].forEach(i => $(`cs-step-${i}`).classList.toggle('hidden', i !== n));
}

function generateAndShowStep2() {
  const emailDest = $('f-dest-email').value.trim();
  const days      = parseInt($('f-dest-days').value);
  const captures  = parseInt($('f-dest-captures').value);

  clearError('cs-error-1');
  if (!emailDest || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailDest)) {
    showError('cs-error-1', 'Ingresa un email destino válido.'); return;
  }
  if (isNaN(days) || days < 1) {
    showError('cs-error-1', 'Los días de acceso deben ser al menos 1.'); return;
  }
  if (isNaN(captures) || captures < 1) {
    showError('cs-error-1', 'Las capturas deben ser al menos 1.'); return;
  }

  // Generar email aleatorio
  const chars  = 'abcdefghjkmnpqrstuvwxyz23456789';
  const suffix = Array.from({length: 6}, () => chars[Math.floor(Math.random() * chars.length)]).join('');
  _genEmail = `user_${suffix}@simpleresolve.com`;

  // Generar contraseña segura (12 chars, con mayúscula, minúscula, dígito y especial)
  const upper   = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  const lower   = 'abcdefghjkmnpqrstuvwxyz';
  const digits  = '23456789';
  const special = '!@#$%';
  const all     = upper + lower + digits + special;
  let pwd = [
    upper[Math.floor(Math.random() * upper.length)],
    lower[Math.floor(Math.random() * lower.length)],
    digits[Math.floor(Math.random() * digits.length)],
    special[Math.floor(Math.random() * special.length)],
    ...Array.from({length: 8}, () => all[Math.floor(Math.random() * all.length)]),
  ];
  for (let i = pwd.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pwd[i], pwd[j]] = [pwd[j], pwd[i]];
  }
  _genPassword = pwd.join('');

  // Poblar paso 2
  $('prev-email-cuenta').textContent  = _genEmail;
  $('prev-password').textContent      = _genPassword;
  $('prev-email-destino').textContent = emailDest;
  $('prev-captures').textContent      = captures;
  $('prev-days').textContent          = `${days} días`;
  clearError('cs-error-2');
  showCreateStep(2);
}

$('btn-generate-creds').addEventListener('click', generateAndShowStep2);
['f-dest-email', 'f-dest-days', 'f-dest-captures'].forEach(id => {
  const el = $(id);
  if (el) el.addEventListener('keydown', e => e.key === 'Enter' && generateAndShowStep2());
});

$('btn-create-confirm').addEventListener('click', confirmCreate);

async function confirmCreate() {
  if (!_genEmail || !_genPassword) {
    showError('cs-error-2', 'Genera las credenciales primero.'); return;
  }
  const emailDest = $('f-dest-email').value.trim();
  const days      = parseInt($('f-dest-days').value);
  const captures  = parseInt($('f-dest-captures').value);

  const btn = $('btn-create-confirm');
  btnLoading(btn, true, 'Creando cuenta…');
  clearError('cs-error-2');

  try {
    const result = await apiFetch('/admin/users/create-with-welcome', {
      method: 'POST',
      body: JSON.stringify({
        email_destino:   emailDest,
        email_cuenta:    _genEmail,
        password_cuenta: _genPassword,
        captures_limite: captures,
        dias_acceso:     days,
      }),
    });

    $('rcpt-email').textContent    = result.email_cuenta;
    $('rcpt-password').textContent = result.password_cuenta;
    $('rcpt-expiry').textContent   = formatDate(result.fecha_vencimiento);
    $('rcpt-captures').textContent = result.captures_limite;
    $('rcpt-destino').textContent  = result.email_destino;
    showCreateStep(3);
    loadUsers();

  } catch (err) {
    showError('cs-error-2', err.detail || 'Error al crear la cuenta.');
  } finally {
    btnLoading(btn, false, 'Crear cuenta y enviar bienvenida ✉');
  }
}

function copyReceipt() {
  const email  = $('rcpt-email').textContent;
  const pwd    = $('rcpt-password').textContent;
  const expiry = $('rcpt-expiry').textContent;
  const caps   = $('rcpt-captures').textContent;
  const text   = [
    'SimpleResolve — Credenciales de acceso',
    '',
    `Email:      ${email}`,
    `Contraseña: ${pwd}`,
    '',
    `Capturas:   ${caps}`,
    `Vencimiento: ${expiry}`,
  ].join('\n');
  navigator.clipboard.writeText(text).then(() => toast('Credenciales copiadas al portapapeles.'));
}

// ── Modal: editar usuario ──────────────────────────────────────────────────────
function openEdit(id) {
  const user = _users.find(u => u.id === id);
  if (!user) return;
  _editingId = id;

  $('modal-title').textContent = 'Editar usuario';
  $('create-fields').classList.add('hidden');
  $('remaining-col').classList.remove('hidden');
  $('active-field').classList.remove('hidden');

  $('f-limite').value     = user.captures_limite ?? user.captures_remaining ?? '';
  $('f-remaining').value  = user.captures_remaining ?? '';
  $('f-active').checked   = user.activo !== false;

  // Días a extender
  $('f-days').value = '';
  $('days-label').textContent = 'Días a extender vencimiento';
  const days = daysUntil(user.fecha_vencimiento);
  if (days !== null) {
    const hint = days >= 0
      ? `Vence en ${days} día(s) (${formatDate(user.fecha_vencimiento)}). Dejar vacío para no cambiar.`
      : `Vencida hace ${Math.abs(days)} día(s). Dejar vacío para no cambiar.`;
    $('days-hint').textContent = hint;
    $('days-hint').classList.remove('hidden');
  } else {
    $('days-hint').classList.add('hidden');
  }

  clearError('modal-error');
  showModal('modal-user');
  $('f-limite').focus();
}

// ── Guardar (crear o editar) ───────────────────────────────────────────────────
$('btn-modal-save').addEventListener('click', saveUser);

async function saveUser() {
  clearError('modal-error');
  const btn = $('btn-modal-save');
  btnLoading(btn, true, 'Guardando…');

  try {
    if (_editingId === null) {
      await createUser();
    } else {
      await editUser(_editingId);
    }
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

  if (!email)           throw { detail: 'El email es obligatorio.' };
  if (!password)        throw { detail: 'La contraseña es obligatoria.' };
  if (password.length < 8) throw { detail: 'La contraseña debe tener al menos 8 caracteres.' };
  if (isNaN(limite) || limite < 0) throw { detail: 'Límite de capturas inválido.' };
  if (isNaN(dias)   || dias < 1)   throw { detail: 'Los días de acceso deben ser al menos 1.' };

  return apiFetch('/admin/users', {
    method: 'POST',
    body: JSON.stringify({ email, password, captures_limite: limite, dias_acceso: dias }),
  });
}

async function editUser(id) {
  const body = {};

  const limite    = $('f-limite').value.trim();
  const remaining = $('f-remaining').value.trim();
  const dias      = $('f-days').value.trim();
  const activo    = $('f-active').checked;

  if (limite    !== '') body.captures_limite    = parseInt(limite);
  if (remaining !== '') body.captures_remaining = parseInt(remaining);
  if (dias      !== '') body.dias_acceso        = parseInt(dias);

  const user = _users.find(u => u.id === id);
  if (user && user.activo !== activo) body.activo = activo;

  if (!Object.keys(body).length) throw { detail: 'No hay cambios que guardar.' };

  if ('captures_limite' in body && isNaN(body.captures_limite))    throw { detail: 'Límite de capturas inválido.' };
  if ('captures_remaining' in body && isNaN(body.captures_remaining)) throw { detail: 'Capturas restantes inválido.' };
  if ('dias_acceso' in body && (isNaN(body.dias_acceso) || body.dias_acceso < 1)) throw { detail: 'Días a extender deben ser al menos 1.' };

  return apiFetch(`/admin/users/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

// ── Modal: eliminar ───────────────────────────────────────────────────────────
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
    await apiFetch(`/admin/users/${_deletingId}`, { method: 'DELETE' });
    closeModal('modal-delete');
    await loadUsers();
    toast('Usuario eliminado.', 'success');
  } catch (err) {
    toast(err.detail || 'Error al eliminar.', 'error');
  } finally {
    btnLoading(btn, false, 'Eliminar');
    _deletingId = null;
  }
});

// ── Copiar secreto TOTP ───────────────────────────────────────────────────────
function copySecret() {
  const secret = $('totp-secret-text').textContent;
  navigator.clipboard.writeText(secret).then(() => toast('Secreto copiado.'));
}

// ── Enter en modal ────────────────────────────────────────────────────────────
['f-email','f-password','f-limite','f-remaining','f-days'].forEach(id => {
  const el = $(id);
  if (el) el.addEventListener('keydown', e => e.key === 'Enter' && saveUser());
});

// ── Modal: enviar bienvenida ──────────────────────────────────────────────────
function openWelcome(id) {
  const user = _users.find(u => u.id === id);
  if (!user) return;
  _welcomingId = id;
  $('f-welcome-email').value    = user.email;
  $('f-welcome-password').value = '';
  clearError('welcome-error');
  showModal('modal-welcome');
  $('f-welcome-password').focus();
}

$('btn-send-welcome').addEventListener('click', sendWelcome);
['f-welcome-email', 'f-welcome-password'].forEach(id => {
  const el = $(id);
  if (el) el.addEventListener('keydown', e => e.key === 'Enter' && sendWelcome());
});

async function sendWelcome() {
  if (!_welcomingId) return;
  const emailDest = $('f-welcome-email').value.trim();
  const password  = $('f-welcome-password').value;
  if (!emailDest) { showError('welcome-error', 'El email es obligatorio.'); return; }
  if (!password)  { showError('welcome-error', 'La contraseña temporal es obligatoria.'); return; }

  const btn = $('btn-send-welcome');
  btnLoading(btn, true, 'Enviando…');
  clearError('welcome-error');

  try {
    await apiFetch(`/admin/users/${_welcomingId}/send-welcome`, {
      method: 'POST',
      body: JSON.stringify({ email_destino: emailDest, temp_password: password }),
    });
    closeModal('modal-welcome');
    await loadUsers();
    toast('Email de bienvenida enviado correctamente.', 'success');
  } catch (err) {
    showError('welcome-error', err.detail || 'Error al enviar el email.');
  } finally {
    btnLoading(btn, false, 'Enviar bienvenida ✉');
    _welcomingId = null;
  }
}

// ── Modal: recargar capturas ──────────────────────────────────────────────────
async function openReload(id) {
  const user = _users.find(u => u.id === id);
  if (!user) return;
  _reloadingId = id;
  $('reload-user-email').textContent       = user.email;
  $('reload-current-captures').textContent = user.captures_remaining ?? '—';
  $('f-reload-amount').value               = '';
  $('f-reload-email').value                = '';
  clearError('reload-error');
  $('reload-history-content').innerHTML    = '<p class="history-empty">Cargando historial…</p>';
  showModal('modal-reload');
  $('f-reload-amount').focus();

  try {
    const history = await apiFetch(`/admin/users/${id}/reload-history`);
    renderReloadHistory(history);
  } catch (_) {
    $('reload-history-content').innerHTML = '<p class="history-empty" style="color:var(--danger)">Error al cargar historial.</p>';
  }
}

function renderReloadHistory(items) {
  if (!items.length) {
    $('reload-history-content').innerHTML = '<p class="history-empty">Sin recargas previas.</p>';
    return;
  }
  const rows = items.map(r => `
    <tr>
      <td>${formatDate(r.created_at)}</td>
      <td><span class="reload-amount-cell">+${r.amount}</span></td>
      <td>${r.captures_total_after}</td>
    </tr>
  `).join('');
  $('reload-history-content').innerHTML = `
    <table class="history-table">
      <thead><tr><th>Fecha</th><th>Agregadas</th><th>Total tras recarga</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

$('btn-confirm-reload').addEventListener('click', sendReload);
$('f-reload-amount').addEventListener('keydown', e => e.key === 'Enter' && sendReload());

async function sendReload() {
  if (!_reloadingId) return;
  const amount       = parseInt($('f-reload-amount').value);
  const emailDestino = $('f-reload-email').value.trim();

  if (isNaN(amount) || amount < 1) {
    showError('reload-error', 'Ingresa una cantidad válida (mínimo 1).');
    return;
  }
  if (!emailDestino) {
    showError('reload-error', 'Ingresa el email del cliente para enviar el aviso.');
    return;
  }

  const btn = $('btn-confirm-reload');
  btnLoading(btn, true, 'Recargando…');
  clearError('reload-error');

  try {
    const result = await apiFetch(`/admin/users/${_reloadingId}/reload-captures`, {
      method: 'POST',
      body: JSON.stringify({ amount, email_destino: emailDestino }),
    });
    closeModal('modal-reload');
    await loadUsers();
    if (result.email_sent) {
      toast(`⚡ ${amount} capturas recargadas. Email enviado a ${emailDestino}.`, 'success');
    } else {
      toast(`⚡ Capturas recargadas (total: ${result.new_remaining}). ⚠ Email no enviado: ${result.email_error || 'error desconocido'}`, 'warning');
    }
  } catch (err) {
    showError('reload-error', err.detail || 'Error al recargar capturas.');
  } finally {
    btnLoading(btn, false, 'Recargar ⚡');
    _reloadingId = null;
  }
}

// ── Modal: detalle de usuario ─────────────────────────────────────────────────
async function openUserDetail(id) {
  $('detail-email-sub').textContent = '';
  $('detail-content').innerHTML = '<p class="history-empty">Cargando…</p>';
  showModal('modal-user-detail');
  try {
    const [data, emailLogs] = await Promise.all([
      apiFetch(`/admin/users/${id}/details`),
      apiFetch(`/admin/users/${id}/email-history`),
    ]);
    renderUserDetail(data, emailLogs);
  } catch (_) {
    $('detail-content').innerHTML = '<p class="history-empty" style="color:var(--danger)">Error al cargar detalle.</p>';
  }
}

function renderUserDetail(data, emailLogs) {
  const user     = data.user || {};
  const timeline = data.timeline || [];
  const logins   = data.login_logs || [];
  const logs     = emailLogs || [];

  $('detail-email-sub').textContent = user.email || '';

  const capturesRemaining = user.captures_remaining ?? '—';
  const capturesLimite    = user.captures_limite    ?? '—';
  const usedTotal         = data.captures_used_total ?? 0;
  const usedToday         = data.captures_used_today ?? 0;

  function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('es-ES', {day:'numeric', month:'short', year:'numeric'});
  }
  function fmtTime(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleTimeString('es-ES', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  }

  // ── Evidencia de correos ──
  const typeLabel = { welcome: 'Bienvenida', reload: 'Recarga' };
  const evidenceRows = logs.length
    ? logs.map(log => {
        const m = (typeof log.metadata === 'string' ? JSON.parse(log.metadata) : log.metadata) || {};
        const details = (log.type === 'reload' && m.amount != null)
          ? `+${m.amount} cap. → ${m.total_after} total`
          : '—';
        const typeClass = log.type === 'welcome' ? 'email-type-welcome' : 'email-type-reload';
        return `<tr>
          <td><span class="email-type-badge ${typeClass}">${typeLabel[log.type] || log.type}</span></td>
          <td class="detail-date">${fmtDate(log.sent_at)}</td>
          <td class="detail-time">${fmtTime(log.sent_at)}</td>
          <td class="detail-evidence-details">${details}</td>
          <td><span class="evidence-status-badge">Enviado</span></td>
          <td><button class="btn btn-ghost evidence-preview-btn" onclick="openEmailPreview('${log.id}')">Ver correo</button></td>
        </tr>`;
      }).join('')
    : '<tr><td colspan="6" class="history-empty" style="text-align:center;padding:12px;">Sin emails enviados aún.</td></tr>';

  // ── Timeline ──
  const timelineRows = timeline.length
    ? timeline.map(e => `<tr>
        <td class="detail-date">${fmtDate(e.timestamp)}</td>
        <td class="detail-time">${fmtTime(e.timestamp)}</td>
        <td class="detail-event">${e.event_type || '—'}</td>
        <td class="detail-ip">${e.ip || '—'}</td>
        <td class="detail-ver">${e.app_version || '—'}</td>
      </tr>`).join('')
    : '<tr><td colspan="5" class="history-empty" style="text-align:center;padding:12px;">Sin actividad registrada.</td></tr>';

  // ── Logins ──
  const loginRows = logins.length
    ? logins.map(l => `<tr>
        <td class="detail-date">${fmtDate(l.logged_at)}</td>
        <td class="detail-time">${fmtTime(l.logged_at)}</td>
        <td class="detail-ip">${l.ip || '—'}</td>
      </tr>`).join('')
    : '<tr><td colspan="3" class="history-empty" style="text-align:center;padding:12px;">Sin inicios de sesión registrados.</td></tr>';

  const ipWarning = data.ip_anomaly
    ? `<div class="detail-ip-warning">⚠ IPs múltiples detectadas en la última hora</div>` : '';

  $('detail-content').innerHTML = `
    <div class="detail-stats-row">
      <div class="detail-stat-card">
        <div class="detail-stat-label">Capturas restantes</div>
        <div class="detail-stat-value">${capturesRemaining}<span class="detail-stat-of"> / ${capturesLimite}</span></div>
      </div>
      <div class="detail-stat-card">
        <div class="detail-stat-label">Capturas usadas (total)</div>
        <div class="detail-stat-value" style="color:var(--accent-h)">${usedTotal}</div>
      </div>
      <div class="detail-stat-card">
        <div class="detail-stat-label">Usadas hoy</div>
        <div class="detail-stat-value" style="color:var(--warning)">${usedToday}</div>
      </div>
    </div>
    ${ipWarning}
    <div class="detail-section">
      <h4 class="history-title">Evidencia de correos enviados</h4>
      <div class="detail-table-scroll">
        <table class="history-table">
          <thead><tr><th>Tipo</th><th>Fecha</th><th>Hora</th><th>Detalles</th><th>Estado</th><th></th></tr></thead>
          <tbody>${evidenceRows}</tbody>
        </table>
      </div>
    </div>
    <div class="detail-section">
      <h4 class="history-title">Timeline de actividad (últimas 20)</h4>
      <div class="detail-table-scroll">
        <table class="history-table">
          <thead><tr><th>Fecha</th><th>Hora</th><th>Evento</th><th>IP</th><th>Versión</th></tr></thead>
          <tbody>${timelineRows}</tbody>
        </table>
      </div>
    </div>
    <div class="detail-section">
      <h4 class="history-title">Últimos 10 inicios de sesión</h4>
      <div class="detail-table-scroll">
        <table class="history-table">
          <thead><tr><th>Fecha</th><th>Hora</th><th>IP</th></tr></thead>
          <tbody>${loginRows}</tbody>
        </table>
      </div>
    </div>`;
}

// ── Modal: preview de correo ──────────────────────────────────────────────────
async function openEmailPreview(logId) {
  $('preview-subject').textContent = '';
  $('preview-iframe').srcdoc = '<html><body style="background:#0f0f1a;color:#888;font-family:Arial,sans-serif;padding:30px;text-align:center;font-size:14px;">Cargando vista previa…</body></html>';
  showModal('modal-email-preview');
  try {
    const data = await apiFetch(`/admin/email-logs/${logId}/preview`);
    $('preview-subject').textContent = `Asunto: ${data.subject}`;
    $('preview-iframe').srcdoc = data.html;
  } catch (_) {
    $('preview-iframe').srcdoc = '<html><body style="background:#0f0f1a;color:#f87171;font-family:Arial,sans-serif;padding:30px;text-align:center;font-size:14px;">Error al cargar la vista previa.</body></html>';
  }
}

// ── Modal: historial de comunicaciones ────────────────────────────────────────
async function openEmailHistory(id, email) {
  _historyUserId = id;
  $('email-history-user').textContent = email;
  $('email-history-content').innerHTML = '<p class="history-empty">Cargando historial…</p>';
  showModal('modal-email-history');
  try {
    const logs = await apiFetch(`/admin/users/${id}/email-history`);
    renderEmailHistory(logs);
  } catch (_) {
    $('email-history-content').innerHTML = '<p class="history-empty" style="color:var(--danger)">Error al cargar historial.</p>';
  }
}

function renderEmailHistory(items) {
  if (!items || !items.length) {
    $('email-history-content').innerHTML = '<p class="history-empty">No se han enviado emails a este usuario.</p>';
    return;
  }
  const typeLabel = { welcome: 'Bienvenida', reload: 'Recarga' };
  const rows = items.map(log => {
    const dt = new Date(log.sent_at);
    const dateStr = dt.toLocaleDateString('es-ES', {day: 'numeric', month: 'short', year: 'numeric'});
    const timeStr = dt.toLocaleTimeString('es-ES', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
    const type = typeLabel[log.type] || log.type;
    const typeClass = log.type === 'welcome' ? 'email-type-welcome' : 'email-type-reload';
    let details = '—';
    if (log.type === 'reload' && log.metadata) {
      const m = typeof log.metadata === 'string' ? JSON.parse(log.metadata) : log.metadata;
      if (m && m.amount != null) details = `+${m.amount} → ${m.total_after}`;
    }
    return `<tr>
      <td><span class="email-type-badge ${typeClass}">${type}</span></td>
      <td><span class="email-date-text">${dateStr}</span><br><span class="email-time-text">${timeStr}</span></td>
      <td class="email-details-cell">${details}</td>
    </tr>`;
  }).join('');
  $('email-history-content').innerHTML = `
    <table class="history-table">
      <thead><tr>
        <th>Tipo</th>
        <th>Fecha y hora</th>
        <th>Detalles</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── Init ──────────────────────────────────────────────────────────────────────
(function init() {
  const saved = _loadSavedToken();
  if (saved) {
    _adminToken = saved;
    showScreen('dashboard');
    loadUsers();
  } else {
    showScreen('login');
    $('inp-password').focus();
  }
})();
