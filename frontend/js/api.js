/* SubstManager v2 – API wrapper */
const BASE = '';
const API = {
  async get(path) {
    const r = await fetch(BASE + path);
    if (!r.ok) throw new Error(`GET ${path}: ${r.status}`);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(BASE + path, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(`POST ${path}: ${r.status}`);
    return r.json();
  },
  async put(path, body) {
    const r = await fetch(BASE + path, {
      method: 'PUT', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(`PUT ${path}: ${r.status}`);
    return r.json();
  },
  async del(path) {
    const r = await fetch(BASE + path, { method: 'DELETE' });
    if (!r.ok) throw new Error(`DELETE ${path}: ${r.status}`);
    return r.json();
  }
};
