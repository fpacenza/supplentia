/* Supplentia v2 – Uscite Didattiche */

let _usciteOggi = [];
let _classiCache = [];

async function loadUscite() {
  // Caricato dalla sezione assenze (stessa data corrente)
  const container = document.getElementById('uscite-list');
  if (!container) return;
  container.innerHTML = '<div class="loading"><div class="spinner"></div>Caricamento…</div>';
  try {
    const data = isoDate(currentDate);
    [_usciteOggi, _classiCache] = await Promise.all([
      API.get(`/api/uscite?data=${data}`),
      _classiCache.length ? Promise.resolve(_classiCache) : API.get('/api/classi')
    ]);
    renderUscite();
  } catch(e) {
    container.innerHTML = `<div style="color:var(--red)">Errore: ${e.message}</div>`;
  }
}

function renderUscite() {
  const container = document.getElementById('uscite-list');
  if (!container) return;

  if (_usciteOggi.length === 0) {
    container.innerHTML = `<div style="color:var(--text3);font-size:.85rem;padding:8px 0">
      Nessuna uscita didattica registrata per ${formatDateIT(currentDate)}.
    </div>`;
    return;
  }

  container.innerHTML = _usciteOggi.map(u => {
    const ore = u.ore || [];
    const oreLabel = ore.length === 6 ? 'Tutto il giorno'
                   : ore.length === 0 ? '—'
                   : ore.map(o => `${o}ª`).join(', ');
    return `
    <div class="uscita-row">
      <span class="badge badge-orange" style="font-size:.75rem">${u.classe_nome}</span>
      <span style="font-size:.82rem;color:var(--text2);flex:1">${oreLabel}</span>
      ${u.note ? `<span style="font-size:.75rem;color:var(--text3)">${u.note}</span>` : ''}
      <button class="btn btn-danger btn-sm" onclick="eliminaUscita(${u.id})">✕</button>
    </div>`;
  }).join('');
}

async function apriNuovaUscita() {
  // Popola select classi
  const sel = document.getElementById('uscita-classe');
  if (!sel) return;
  if (!_classiCache.length) _classiCache = await API.get('/api/classi');
  sel.innerHTML = '<option value="">Seleziona classe…</option>' +
    [..._classiCache].sort((a,b) => a.nome.localeCompare(b.nome))
      .map(c => `<option value="${c.id}">${c.nome}</option>`).join('');

  // Reset ore: tutte selezionate di default
  document.querySelectorAll('.uscita-ora-chk').forEach(chk => chk.checked = true);
  const noteEl = document.getElementById('uscita-note');
  if (noteEl) noteEl.value = '';

  openModal('nuova-uscita');
}

async function salvaUscita() {
  const classeId = document.getElementById('uscita-classe')?.value;
  if (!classeId) { showToast('Seleziona una classe', 'error'); return; }

  const ore = Array.from(document.querySelectorAll('.uscita-ora-chk:checked'))
    .map(chk => parseInt(chk.value));
  if (!ore.length) { showToast('Seleziona almeno un\'ora', 'error'); return; }

  const note = document.getElementById('uscita-note')?.value?.trim() || '';
  const data = isoDate(currentDate);

  try {
    await API.post('/api/uscite', { classe_id: parseInt(classeId), data, ore, note });
    closeModal('nuova-uscita');
    showToast('Uscita didattica registrata', 'success');
    await loadUscite();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

async function eliminaUscita(id) {
  try {
    await API.del(`/api/uscite/${id}`);
    showToast('Uscita rimossa', 'info');
    await loadUscite();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}
