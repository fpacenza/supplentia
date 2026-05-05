/* SubstManager v2 – Assenze */

let _docentiCache = [];

async function loadAssenze() {
  const data = isoDate(currentDate);
  const tbody = document.getElementById('assenze-table');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7"><div class="loading"><div class="spinner"></div>Caricamento…</div></td></tr>';
  try {
    const rows = await API.get(`/api/assenze?data=${data}`);
    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text3);text-align:center;padding:20px">Nessuna assenza registrata per questa data</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(a => {
      const ore = JSON.parse(a.ore_json || '[]');
      return `<tr>
        <td><div class="td-name">${a.docente_nome}</div><div class="td-sub">${a.materia||''}</div></td>
        <td><span class="badge badge-gray">${a.data}</span></td>
        <td>${causaBadge(a.tipo)}</td>
        <td><span style="font-family:var(--mono);font-size:.8rem">${ore.map(o=>o+'ª').join(', ')}</span></td>
        <td><span style="color:var(--text3);font-size:.78rem">${a.note||'—'}</span></td>
        <td><span class="badge badge-blue">${ore.length} slot</span></td>
        <td>
          <div style="display:flex;gap:4px">
            <button class="btn btn-danger btn-sm" onclick="eliminaAssenza(${a.id}, this)">✕</button>
          </div>
        </td>
      </tr>`;
    }).join('');
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="7" style="color:var(--red)">Errore: ' + e.message + '</td></tr>';
  }
}

async function eliminaAssenza(id, btn) {
  if (!confirm('Eliminare questa assenza?\n\nLe sostituzioni associate verranno rimosse e il motore ricalcolerà automaticamente gli slot rimasti scoperti.')) return;
  try {
    await API.del(`/api/assenze/${id}`);
    showToast('Assenza eliminata · Sostituzioni ricalcolate', 'info');
    loadAssenze();
    // Ricarica dashboard/sostituzioni se attive
    if (currentView === 'dashboard') loadDashboard();
    else if (currentView === 'sostituzioni') loadSostituzioni();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

async function registraAssenza() {
  const docId = document.getElementById('nuova-assenza-docente')?.value;
  const data  = document.getElementById('nuova-assenza-data')?.value;
  const tipo  = document.getElementById('nuova-assenza-tipo')?.value;
  const note  = document.getElementById('nuova-assenza-note')?.value;
  const ore   = [...document.querySelectorAll('.ore-check:checked')].map(c=>parseInt(c.value));

  if (!docId || docId === '0') { showToast('Seleziona un docente', 'error'); return; }
  if (!data) { showToast('Inserisci la data', 'error'); return; }
  if (ore.length === 0) { showToast('Seleziona almeno un\'ora', 'error'); return; }

  try {
    const risposta = await API.post('/api/assenze', { docente_id: parseInt(docId), data, tipo, ore_json: JSON.stringify(ore), note });
    closeModal('nuova-assenza');

    // Se il docente era già sostituto da qualche parte, il server ha già ricalcolato
    if (risposta.conflitti_riaperti > 0) {
      showToast(
        `⚠ ${risposta.conflitti_riaperti} sostituzione/i invalidata/e: il docente era già assegnato come sostituto · Ricalcolo automatico eseguito`,
        'info', 5000
      );
    } else {
      showToast('Assenza registrata', 'success');
    }

    loadAssenze();

    // Auto-run engine (calcola le sostituzioni per questa assenza)
    const res = await API.post('/api/engine/run', { data });
    const msg = res.coperte > 0
      ? `✓ ${res.coperte}/${res.slot_totali} sostituzioni generate`
      : res.slot_totali === 0
        ? 'Nessuno slot da coprire'
        : `⚠ ${res.non_coperte} sostituzioni non coperte`;
    showToast(msg, res.non_coperte > 0 ? 'error' : 'teal');

    // Ricarica le viste attive
    if (currentView === 'dashboard') loadDashboard();
    else if (currentView === 'sostituzioni') loadSostituzioni();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

async function prepareNuovaAssenza() {
  // Popola select docenti – ricarica sempre (i docenti possono essere cambiati)
  const sel = document.getElementById('nuova-assenza-docente');
  if (!sel) return;
  _docentiCache = await API.get('/api/docenti');
  if (_docentiCache.length === 0) {
    showToast('Nessun docente registrato. Aggiungi prima i docenti.', 'error');
    return;
  }
  sel.innerHTML = '<option value="0">Seleziona docente…</option>' +
    _docentiCache.map(d => `<option value="${d.id}">${d.cognome} ${d.nome}${d.materia ? ' – ' + d.materia : ''}</option>`).join('');
  // Data di default = currentDate
  const dataEl = document.getElementById('nuova-assenza-data');
  if (dataEl) dataEl.value = isoDate(currentDate);
  // Reset ore
  document.querySelectorAll('.ore-check').forEach(c => c.checked = false);
  // Reset note
  const noteEl = document.getElementById('nuova-assenza-note');
  if (noteEl) noteEl.value = '';
  openModal('nuova-assenza');
}
