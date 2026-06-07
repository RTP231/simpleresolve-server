'use strict';

// ── Configuración ─────────────────────────────────────────────────────────────
const API_BASE = 'https://simpleresolve-server-production.up.railway.app';

// ── Estado ────────────────────────────────────────────────────────────────────
let _step1Token   = null;
let _adminToken   = null;
let _users        = [];
let _editingId    = null;   // null = crear, string = editar
let _deletingId   = null;
let _toastTimer   = null;

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
      // Primera vez: mostrar QR
      $('qr-setup').classList.remove('hidden');
      $('totp-secret-text').textContent = data.totp_secret;
      $('secret-env').textContent = data.totp_secret;
      QRCode.toCanvas($('qr-canvas'), data.totp_uri, { width: 192, margin: 1 });
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

function renderUsers() {
  if (!_users.length) {
    $('users-tbody').innerHTML = '<tr><td colspan="5" class="empty-row">No hay usuarios registrados.</td></tr>';
    return;
  }

  $('users-tbody').innerHTML = _users.map(u => `
    <tr>
      <td class="col-email"><span class="email-text">${escHtml(u.email)}</span></td>
      <td><span class="captures-text">${capturesText(u)}</span></td>
      <td>${expiryHTML(u.fecha_vencimiento)}</td>
      <td>${statusBadge(u)}</td>
      <td class="col-actions">
        <div class="actions-cell">
          <button class="btn-icon" title="Editar" onclick="openEdit('${u.id}')">✎</button>
          <button class="btn-icon danger" title="Eliminar" onclick="openDelete('${u.id}','${escHtml(u.email)}')">🗑</button>
        </div>
      </td>
    </tr>
  `).join('');
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Modal: crear usuario ───────────────────────────────────────────────────────
$('btn-new-user').addEventListener('click', openCreate);

function openCreate() {
  _editingId = null;
  $('modal-title').textContent = 'Nuevo usuario';
  $('create-fields').classList.remove('hidden');
  $('remaining-col').classList.add('hidden');
  $('active-field').classList.add('hidden');
  $('days-label').textContent = 'Días de acceso';
  $('days-hint').classList.add('hidden');
  $('f-email').value    = '';
  $('f-password').value = '';
  $('f-limite').value   = '200';
  $('f-days').value     = '30';
  $('f-active').checked = true;
  clearError('modal-error');
  showModal('modal-user');
  $('f-email').focus();
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

// ── Init ──────────────────────────────────────────────────────────────────────
showScreen('login');
$('inp-password').focus();
