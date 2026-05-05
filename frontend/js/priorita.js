/* Supplentia v2 – Priorità criteri (con add/remove custom) */

let _criteriState = [];

async function loadPriorita() {
  const list = document.getElementById('priority-list');
  if (!list) return;
  list.innerHTML = '<div class="loading"><div class="spinner"></div>Caricamento…</div>';
  try {
    const cfg = await API.get('/api/config');
    const tutti = [...(cfg.criteri||[]), ...(cfg.criteri_custom||[])]
      .sort((a,b) => (a.priorita||99)-(b.priorita||99));
    _criteriState = tutti;
    renderPriorityList(tutti);
  } catch(e) {
    showToast('Errore caricamento criteri', 'error');
  }
}

function renderPriorityList(criteri) {
  const list = document.getElementById('priority-list');
  if (!list) return;
  list.innerHTML = criteri.map((c, i) => {
    const isFixed    = !c.rimuovibile;
    const isCompr    = c.id === 'compresenza';
    const colorDot   = c.colore || '#888';
    const draggable  = isCompr ? 'false' : 'true';
    const fixedClass = isCompr ? 'fixed' : '';
    const dragEvents = isCompr ? '' : `ondragstart="dragStart(event)" ondragover="dragOver(event)" ondrop="dropItem(event)" ondragleave="dragLeave(event)"`;
    return `
    <div class="priority-item ${fixedClass}" draggable="${draggable}" data-id="${c.id}" ${dragEvents}>
      <span class="priority-handle">⠿</span>
      <div class="priority-num">${i+1}</div>
      <div style="width:10px;height:10px;border-radius:50%;background:${colorDot};flex-shrink:0"></div>
      <div class="priority-content">
        <div class="priority-name">${c.nome} ${isCompr ? '<span class="badge badge-teal" style="margin-left:6px;font-size:.62rem">P0 FISSO</span>' : ''}</div>
        <div class="priority-desc">${c.descrizione}</div>
      </div>
      ${!isCompr ? `<div class="toggle ${c.attivo ? 'on' : ''}" onclick="toggleCriterio('${c.id}', this)"></div>` : '<div style="width:36px"></div>'}
      ${c.rimuovibile ? `<button class="btn btn-danger btn-sm" onclick="removeCriterio('${c.id}')">✕</button>` : '<div style="width:30px"></div>'}
    </div>`;
  }).join('');
}

function toggleCriterio(id, el) {
  el.classList.toggle('on');
  const c = _criteriState.find(x => x.id === id);
  if (c) c.attivo = el.classList.contains('on');
}

async function removeCriterio(id) {
  if (!confirm('Rimuovere questo criterio custom?')) return;
  try {
    await API.del(`/api/criteri/${id}`);
    showToast('Criterio rimosso', 'info');
    loadPriorita();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

async function savePriorities() {
  const list = document.getElementById('priority-list');
  if (!list) return;
  const items = [...list.querySelectorAll('.priority-item')];
  const aggiornati = items.map((el, i) => {
    const id = el.dataset.id;
    const orig = _criteriState.find(c => c.id === id) || {};
    const toggled = el.querySelector('.toggle');
    return { ...orig, priorita: i+1, attivo: toggled ? toggled.classList.contains('on') : true };
  });
  try {
    await API.put('/api/criteri', aggiornati);
    showToast('Configurazione salvata', 'success');
    _criteriState = aggiornati;
  } catch(e) {
    showToast('Errore salvataggio: ' + e.message, 'error');
  }
}

async function resetPriorities() {
  if (!confirm('Ripristinare l\'ordine di default?')) return;
  try {
    const cfg = await API.get('/api/config');
    _criteriState = [...(cfg.criteri||[]), ...(cfg.criteri_custom||[])];
    renderPriorityList(_criteriState);
    showToast('Ordine ripristinato', 'info');
  } catch(e) {
    showToast('Errore', 'error');
  }
}

function openAddCriterio() { openModal('add-criterio'); }

async function saveNewCriterio() {
  const nome = document.getElementById('nc-nome')?.value?.trim();
  const desc = document.getElementById('nc-desc')?.value?.trim();
  const col  = document.getElementById('nc-colore')?.value || '#888888';
  if (!nome) { showToast('Nome obbligatorio', 'error'); return; }
  try {
    await API.post('/api/criteri', { nome, descrizione: desc, colore: col, parametri:{} });
    closeModal('add-criterio');
    showToast('Criterio aggiunto', 'teal');
    loadPriorita();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}
