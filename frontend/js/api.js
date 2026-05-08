/* SubstManager v2 – API wrapper con autenticazione */
const BASE = '';

function _authHeaders(extra = {}) {
  const token = localStorage.getItem('sm_token') || '';
  return {
    ...extra,
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  };
}

async function _handle(r, label) {
  if (r.status === 401) {
    // Non autenticato: reindirizza al login
    localStorage.removeItem('sm_token');
    window.location.href = '/login';
    throw new Error('Non autenticato');
  }
  if (!r.ok) {
    let msg = `${label}: ${r.status}`;
    try { const d = await r.json(); if (d.errore) msg = d.errore; } catch(_) {}
    throw new Error(msg);
  }
  return r.json();
}

const API = {
  async get(path) {
    const r = await fetch(BASE + path, {
      credentials: 'include',
      headers: _authHeaders()
    });
    return _handle(r, `GET ${path}`);
  },
  async post(path, body) {
    const r = await fetch(BASE + path, {
      method: 'POST',
      credentials: 'include',
      headers: _authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body)
    });
    return _handle(r, `POST ${path}`);
  },
  async put(path, body) {
    const r = await fetch(BASE + path, {
      method: 'PUT',
      credentials: 'include',
      headers: _authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body)
    });
    return _handle(r, `PUT ${path}`);
  },
  async del(path) {
    const r = await fetch(BASE + path, {
      method: 'DELETE',
      credentials: 'include',
      headers: _authHeaders()
    });
    return _handle(r, `DELETE ${path}`);
  }
};
