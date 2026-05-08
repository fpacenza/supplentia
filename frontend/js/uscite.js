/* Supplentia – Uscite Didattiche */

let _usciteOggi = [];
let _classiCache = [];

async function loadUscite() {
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
      Nessuna uscita didattica attiva per ${formatDateIT(currentDate)}.
    </div>`;
    return;
  }

  // Raggruppa per classe+ore+note per mostrare una sola riga per range
  // (ogni giorno del range è una riga separata nel DB → le raggruppiamo visivamente)
  const gruppi = {};
  _usciteOggi.forEach(u => {
    const key = `${u.classe_id}|${u.ore_json}|${u.note}`;
    if (!gruppi[key]) {
      gruppi[key] = { ...u, data_min: u.data, data_max: u.data_fine || u.data, ids: [u.id] };
    } else {
      gruppi[key].ids.push(u.id);
      if (u.data < gruppi[key].data_min) gruppi[key].data_min = u.data;
      if ((u.data_fine || u.data) > gruppi[key].data_max) gruppi[key].data_max = u.data_fine || u.data;
    }
  });

  container.innerHTML = Object.values(gruppi).map(u => {
    const ore = u.ore || [];
    const oreLabel = ore.length === 6 ? 'Tutto il giorno'
                   : ore.length === 0 ? '—'
                   : ore.map(o => `${o}ª`).join(', ');

    // Range date
    const fmtDate = iso => {
      const [y,m,d] = iso.split('-');
      return `${d}/${m}/${y}`;
    };
    const rangeLabel = u.data_min === u.data_max
      ? fmtDate(u.data_min)
      : `${fmtDate(u.data_min)} → ${fmtDate(u.data_max)}`;

    return `
    <div class="uscita-row">
      <span class="badge badge-orange" style="font-size:.75rem;flex-shrink:0">${u.classe_nome}</span>
      <span style="font-size:.82rem;color:var(--accent);font-family:var(--mono);flex-shrink:0">${rangeLabel}</span>
      <span style="font-size:.8rem;color:var(--text2);flex:1">${oreLabel}</span>
      ${u.note ? `<span style="font-size:.72rem;color:var(--text3);font-style:italic">${u.note}</span>` : ''}
      <button class="btn btn-danger btn-sm" onclick="eliminaUscita(${JSON.stringify(u.ids)})">✕</button>
    </div>`;
  }).join('');
}

async function apriNuovaUscita() {
  const sel = document.getElementById('uscita-classe');
  if (!sel) return;
  if (!_classiCache.length) _classiCache = await API.get('/api/classi');
  sel.innerHTML = '<option value="">Seleziona classe…</option>' +
    [..._classiCache].sort((a,b) => a.nome.localeCompare(b.nome))
      .map(c => `<option value="${c.id}">${c.nome}</option>`).join('');

  // Data inizio = data corrente, data fine = data corrente
  const dataStr = isoDate(currentDate);
  const inizio = document.getElementById('uscita-data-inizio');
  const fine   = document.getElementById('uscita-data-fine');
  if (inizio) inizio.value = dataStr;
  if (fine)   fine.value   = dataStr;

  // Reset ore: tutte selezionate
  document.querySelectorAll('.uscita-ora-chk').forEach(chk => chk.checked = true);
  const noteEl = document.getElementById('uscita-note');
  if (noteEl) noteEl.value = '';

  openModal('nuova-uscita');
}

async function salvaUscita() {
  const classeId  = document.getElementById('uscita-classe')?.value;
  const dataInizio = document.getElementById('uscita-data-inizio')?.value;
  const dataFine   = document.getElementById('uscita-data-fine')?.value;

  if (!classeId)   { showToast('Seleziona una classe', 'error'); return; }
  if (!dataInizio) { showToast('Inserisci la data di inizio', 'error'); return; }

  const dataF = dataFine && dataFine >= dataInizio ? dataFine : dataInizio;

  const ore = Array.from(document.querySelectorAll('.uscita-ora-chk:checked'))
    .map(chk => parseInt(chk.value));
  if (!ore.length) { showToast("Seleziona almeno un'ora", 'error'); return; }

  const note = document.getElementById('uscita-note')?.value?.trim() || '';

  // Calcola il numero di giorni
  const nGiorni = Math.round((new Date(dataF) - new Date(dataInizio)) / 86400000) + 1;
  const btnText = nGiorni > 1
    ? `Registra (${nGiorni} giorni)`
    : 'Registra';

  try {
    const resp = await API.post('/api/uscite', {
      classe_id: parseInt(classeId),
      data: dataInizio,
      data_fine: dataF,
      ore,
      note
    });
    closeModal('nuova-uscita');
    const msg = resp.giorni > 1
      ? `✓ Uscita registrata per ${resp.giorni} giorni · Sostituzioni ricalcolate`
      : '✓ Uscita didattica registrata · Sostituzioni ricalcolate';
    showToast(msg, 'success');
    // Ricalcolo forzato anche sul client per aggiornare la vista corrente
    await API.post('/api/engine/run', {
      data: isoDate(currentDate),
      forza_ricalcolo: true
    });
    await loadUscite();
    if (typeof loadSostituzioni === 'function') loadSostituzioni();
    if (typeof loadDashboard === 'function') loadDashboard();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

async function eliminaUscita(ids) {
  const idList = Array.isArray(ids) ? ids : [ids];
  if (!confirm(`Rimuovere questa uscita didattica?\nLe sostituzioni verranno ricalcolate da capo.`)) return;
  try {
    // Elimina tutti i giorni del range
    for (const id of idList) {
      await API.del(`/api/uscite/${id}`);
    }
    // Il server ha già fatto run_engine(forza=True) per le date con assenze.
    // Richiediamo anche noi un ricalcolo forzato per la data corrente
    // così la vista si aggiorna immediatamente senza cliccare manualmente.
    await API.post('/api/engine/run', {
      data: isoDate(currentDate),
      forza_ricalcolo: true
    });
    showToast('Uscita rimossa · Sostituzioni ricalcolate da capo', 'success');
    await loadUscite();
    if (typeof loadSostituzioni === 'function') loadSostituzioni();
    if (typeof loadDashboard === 'function') loadDashboard();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

// Sincronizza data fine >= data inizio quando si cambia la data inizio
function syncDataFine() {
  const inizio = document.getElementById('uscita-data-inizio')?.value;
  const fine   = document.getElementById('uscita-data-fine');
  if (!inizio || !fine) return;
  if (!fine.value || fine.value < inizio) fine.value = inizio;
  // Aggiorna testo pulsante con numero giorni
  _aggiornaBtnUscita();
}

function _aggiornaBtnUscita() {
  const inizio = document.getElementById('uscita-data-inizio')?.value;
  const fine   = document.getElementById('uscita-data-fine')?.value;
  const btn    = document.getElementById('btn-salva-uscita');
  if (!btn || !inizio) return;
  const dataFine = fine && fine >= inizio ? fine : inizio;
  const n = Math.round((new Date(dataFine) - new Date(inizio)) / 86400000) + 1;
  btn.textContent = n > 1 ? `Registra (${n} giorni)` : 'Registra';
}
