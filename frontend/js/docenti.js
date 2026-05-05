/* Supplentia v2 – Docenti con griglia orario e compresenze */

let _allDocenti    = [];
let _allClassi     = [];
let _orarioDocente = {};    // cache: docente_id → [slots con compresenza_partners]
let _docente_aperto = null;

const DOC_GIORNI      = ['', 'Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab'];
const DOC_GIORNI_FULL = ['', 'Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato'];
const DOC_ORE         = [1, 2, 3, 4, 5, 6];
const DOC_COLORS      = ['#4f8ef7','#2ec27e','#e5534b','#a47ff0','#e8924a','#f0c040','#00d4a8','#e87ca8'];

const TIPO_INFO = {
  'lezione':       { label: 'Lezione',    col: '#4f8ef7', bg: 'rgba(79,142,247,.15)'  },
  'lezione-pdf':   { label: 'Lezione',    col: '#4f8ef7', bg: 'rgba(79,142,247,.15)'  },
  'disposizione':  { label: 'Disp.',      col: '#2ec27e', bg: 'rgba(46,194,126,.15)'  },
  'potenziamento': { label: 'Poten.',     col: '#00d4a8', bg: 'rgba(0,212,168,.15)'   },
  'sostegno':      { label: 'Sostegno',   col: '#a47ff0', bg: 'rgba(164,127,240,.15)' },
};

// ─────────────────────────── LOAD ───────────────────────────

async function loadDocenti() {
  const container = document.getElementById('docenti-list');
  if (!container) return;
  container.innerHTML = '<div class="loading"><div class="spinner"></div>Caricamento…</div>';
  try {
    [_allDocenti, _allClassi] = await Promise.all([
      API.get('/api/docenti'),
      API.get('/api/classi')
    ]);
    renderDocenti(_allDocenti);
  } catch(e) {
    container.innerHTML = `<div style="color:var(--red);padding:16px">Errore: ${e.message}</div>`;
  }
}

// ─────────────────────────── RENDER LISTA ───────────────────────────

function renderDocenti(rows) {
  const container = document.getElementById('docenti-list');
  if (!container) return;

  if (rows.length === 0) {
    container.innerHTML = `
      <div style="text-align:center;padding:40px 20px;color:var(--text3)">
        <div style="font-size:2.5rem;margin-bottom:12px">👤</div>
        <div style="font-size:.95rem;font-weight:500;color:var(--text2);margin-bottom:6px">Nessun docente nel registro</div>
        <div style="font-size:.8rem">Aggiungi con <strong style="color:var(--accent2)">＋ Docente</strong> o importa dal PDF.</div>
      </div>`;
    return;
  }

  const roleBadge = { curriculare:'badge-blue', sostegno:'badge-purple', potenziamento:'badge-teal' };

  container.innerHTML = rows.map((d, i) => {
    const init  = (d.cognome[0]||'').toUpperCase() + (d.nome?.[0]||'').toUpperCase();
    const col   = DOC_COLORS[i % DOC_COLORS.length];
    const rb    = roleBadge[d.ruolo] || 'badge-gray';
    const open  = _docente_aperto === d.id;
    return `
    <div class="teacher-card-wrap" id="wrap-${d.id}">
      <div class="teacher-card ${open ? 'active' : ''}" data-id="${d.id}" onclick="toggleOrario(${d.id}, this)">
        <div class="teacher-avatar" style="background:linear-gradient(135deg,${col},${col}99);color:#fff;font-size:.82rem">${init}</div>
        <div class="teacher-body">
          <div class="teacher-name">${d.cognome} ${d.nome}</div>
          <div class="teacher-meta">${d.materia||'—'} · ${d.plesso_nome||'Sede Centrale'} · ${d.ruolo}</div>
          <div class="chip-list">
            <span class="chip">Cattedra: ${d.ore_cattedra}h</span>
            ${d.disp_ore_eccedenti ? '<span class="chip" style="color:var(--green)">Disp. ore ecc.</span>' : ''}
            ${d.escluso_motore     ? '<span class="chip" style="color:var(--red)">Escluso motore</span>' : ''}
          </div>
        </div>
        <span class="badge ${rb}" style="flex-shrink:0">${d.ruolo}</span>
        <span class="doc-arrow" style="color:var(--text3);font-size:.8rem;flex-shrink:0">${open ? '▲' : '▼'}</span>
        <button class="btn btn-danger btn-sm" onclick="event.stopPropagation();eliminaDocente(${d.id},'${d.cognome} ${d.nome}')">✕</button>
      </div>
      <div class="orario-panel" id="panel-${d.id}" style="display:${open ? 'block' : 'none'}">
        <div class="loading"><div class="spinner"></div>Caricamento orario…</div>
      </div>
    </div>`;
  }).join('');

  if (_docente_aperto) renderOrarioPanel(_docente_aperto);
}

// ─────────────────────────── TOGGLE ───────────────────────────

async function toggleOrario(docId, cardEl) {
  const panel = document.getElementById(`panel-${docId}`);
  if (!panel) return;

  if (_docente_aperto === docId) {
    panel.style.display = 'none';
    cardEl.classList.remove('active');
    cardEl.querySelector('.doc-arrow').textContent = '▼';
    _docente_aperto = null;
    return;
  }

  if (_docente_aperto) {
    const prev = document.getElementById(`panel-${_docente_aperto}`);
    const prevCard = document.querySelector(`.teacher-card[data-id="${_docente_aperto}"]`);
    if (prev) prev.style.display = 'none';
    if (prevCard) {
      prevCard.classList.remove('active');
      const arr = prevCard.querySelector('.doc-arrow');
      if (arr) arr.textContent = '▼';
    }
  }

  _docente_aperto = docId;
  panel.style.display = 'block';
  cardEl.classList.add('active');
  cardEl.querySelector('.doc-arrow').textContent = '▲';
  await renderOrarioPanel(docId);
}

// ─────────────────────────── GRIGLIA ORARIO ───────────────────────────

async function renderOrarioPanel(docId) {
  const panel = document.getElementById(`panel-${docId}`);
  if (!panel) return;

  // Forza ricaricamento dalla cache o dal server
  try {
    _orarioDocente[docId] = await API.get(`/api/orario?docente_id=${docId}`);
  } catch(e) {
    panel.innerHTML = `<div style="color:var(--red);padding:12px">Errore: ${e.message}</div>`;
    return;
  }

  const slots = _orarioDocente[docId];

  // Mappa giorno → ora → slot (gestisce compresenze: può esserci più di un docente per slot)
  const slotMap = {};
  slots.forEach(s => {
    if (!slotMap[s.giorno]) slotMap[s.giorno] = {};
    slotMap[s.giorno][s.ora] = s;
  });

  const totLezioni  = slots.filter(s => s.tipo === 'lezione' || s.tipo === 'lezione-pdf').length;
  const totDisp     = slots.filter(s => s.tipo === 'disposizione' || s.tipo === 'potenziamento').length;
  const totComp     = slots.filter(s => s.ha_compresenza).length;

  const headerGiorni = [1,2,3,4,5,6].map(g =>
    `<div class="og-header">${DOC_GIORNI[g]}</div>`
  ).join('');

  const righeOre = DOC_ORE.map(ora => {
    const cells = [1,2,3,4,5,6].map(giorno => {
      const slot = slotMap[giorno]?.[ora];
      if (!slot) {
        return `<div class="og-cell og-empty"
                     onclick="apriEditSlot(${docId},${giorno},${ora},null)"
                     title="Aggiungi slot ${DOC_GIORNI_FULL[giorno]} ${ora}ª ora">＋</div>`;
      }
      const ti      = TIPO_INFO[slot.tipo] || TIPO_INFO['lezione'];
      const classe  = slot.classe_nome || '—';
      const materia = (slot.materia || '').substring(0, 16);
      const comp    = slot.ha_compresenza;
      const partners = (slot.compresenza_partners || []).map(p => p.nome.split(' ')[0]).join(', ');
      const tooltip = `${DOC_GIORNI_FULL[giorno]} ${ora}ª – ${classe}`
        + (materia ? ` – ${slot.materia}` : '')
        + (comp ? ` · Compresenza: ${partners}` : '');
      return `<div class="og-cell og-filled${comp ? ' og-comp' : ''}"
                   style="background:${ti.bg};border-color:${ti.col}30"
                   onclick="apriEditSlot(${docId},${giorno},${ora},${slot.id})"
                   title="${tooltip}">
                <div class="og-classe">${classe}</div>
                ${materia ? `<div class="og-materia">${materia}</div>` : ''}
                <div class="og-tipo" style="color:${ti.col}">${ti.label}</div>
                ${comp ? `<div class="og-comp-badge" title="Compresenza con ${partners}">⟳</div>` : ''}
              </div>`;
    }).join('');
    return `<div class="og-ora-label">${ora}ª</div>${cells}`;
  }).join('');

  panel.innerHTML = `
    <div class="orario-panel-inner">
      <div class="orario-panel-head">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <span style="font-weight:600;font-size:.9rem">Orario settimanale</span>
          <span class="chip">${totLezioni} lezioni</span>
          ${totDisp ? `<span class="chip" style="color:var(--green)">${totDisp} disp.</span>` : ''}
          ${totComp ? `<span class="chip" style="color:var(--teal)">⟳ ${totComp} compresenze</span>` : ''}
        </div>
        <div style="display:flex;gap:6px">
          <button class="btn btn-secondary btn-sm" onclick="svuotaOrario(${docId})">🗑 Svuota</button>
        </div>
      </div>

      <div class="orario-grid">
        <div class="og-corner"></div>
        ${headerGiorni}
        ${righeOre}
      </div>

      <div class="orario-legenda">
        ${Object.entries(TIPO_INFO).filter(([k]) => k !== 'lezione-pdf').map(([k, v]) =>
          `<span class="og-leg-item">
            <span style="display:inline-block;width:9px;height:9px;border-radius:2px;
              background:${v.bg};border:1px solid ${v.col};margin-right:3px"></span>${v.label}
          </span>`
        ).join('')}
        <span class="og-leg-item" style="color:var(--teal)">⟳ Compresenza</span>
        <span style="color:var(--text3);font-size:.68rem"> · clicca cella per modificare</span>
      </div>
    </div>`;
}

// ─────────────────────────── MODAL EDIT SLOT ───────────────────────────

let _editCtx = null;

async function apriEditSlot(docId, giorno, ora, slotId) {
  _editCtx = { docId, giorno, ora, slotId };

  const slot = slotId ? (_orarioDocente[docId] || []).find(s => s.id === slotId) : null;

  // Titolo
  document.getElementById('es-titolo').textContent =
    `${DOC_GIORNI_FULL[giorno]} – ${ora}ª ora`;

  // Tipo
  const tipoSel = document.getElementById('es-tipo');
  if (tipoSel) tipoSel.value = (slot?.tipo || 'lezione').replace('-pdf', '');

  // Classe – ordina per nome
  const classeSel = document.getElementById('es-classe');
  if (classeSel) {
    const classiOrd = [..._allClassi].sort((a, b) => a.nome.localeCompare(b.nome));
    classeSel.innerHTML = '<option value="">— Nessuna classe (libero/disp.) —</option>' +
      classiOrd.map(c =>
        `<option value="${c.id}" ${slot?.classe_id == c.id ? 'selected' : ''}>${c.nome}</option>`
      ).join('');
  }

  // Materia
  const materiaEl = document.getElementById('es-materia');
  if (materiaEl) materiaEl.value = slot?.materia || '';

  // Info compresenza esistente
  const compInfo = document.getElementById('es-comp-info');
  if (compInfo) {
    const partners = slot?.compresenza_partners || [];
    if (partners.length > 0) {
      compInfo.style.display = 'flex';
      compInfo.innerHTML = `<span style="color:var(--teal)">⟳ Compresenza con:</span>
        <span style="font-weight:500">${partners.map(p => p.nome).join(', ')}</span>`;
    } else {
      compInfo.style.display = 'none';
    }
  }

  // Nota: se nella stessa classe+giorno+ora c'è già un altro docente, lo mostro
  const compSuggest = document.getElementById('es-comp-suggest');
  if (compSuggest && classeSel?.value) {
    await aggiornaCompresenzaSuggerimento(parseInt(classeSel.value), giorno, ora, docId, slotId);
  } else if (compSuggest) {
    compSuggest.style.display = 'none';
  }

  // Pulsante elimina
  const btnDel = document.getElementById('es-btn-elimina');
  if (btnDel) btnDel.style.display = slotId ? 'inline-flex' : 'none';

  openModal('edit-slot');

  // Aggiorna suggerimento compresenza quando cambia la classe
  if (classeSel) {
    classeSel.onchange = async () => {
      const cid = parseInt(classeSel.value);
      if (cid) await aggiornaCompresenzaSuggerimento(cid, giorno, ora, docId, slotId);
      else if (compSuggest) compSuggest.style.display = 'none';
    };
  }
}

async function aggiornaCompresenzaSuggerimento(classeId, giorno, ora, docId, slotId) {
  const compSuggest = document.getElementById('es-comp-suggest');
  if (!compSuggest) return;

  // Cerca altri docenti che hanno già uno slot in questa classe+giorno+ora
  try {
    const tuttoOrario = await API.get(`/api/orario?classe_id=${classeId}&giorno=${giorno}&ora=${ora}`);
    const altri = tuttoOrario.filter(s => s.docente_id !== docId);
    if (altri.length > 0) {
      const nomi = altri.map(s => {
        const d = _allDocenti.find(x => x.id === s.docente_id);
        return d ? `${d.cognome} ${d.nome}` : `ID ${s.docente_id}`;
      }).join(', ');
      compSuggest.style.display = 'flex';
      compSuggest.innerHTML = `
        <span style="color:var(--teal);font-size:.8rem">⟳</span>
        <span style="font-size:.8rem">Già presente in questa classe/ora: <strong>${nomi}</strong> → verrà creata compresenza automaticamente</span>`;
    } else {
      compSuggest.style.display = 'none';
    }
  } catch(e) {
    compSuggest.style.display = 'none';
  }
}

async function salvaSlot() {
  if (!_editCtx) return;
  const { docId, giorno, ora, slotId } = _editCtx;

  const tipo      = document.getElementById('es-tipo')?.value || 'lezione';
  const classeId  = document.getElementById('es-classe')?.value || null;
  const materia   = document.getElementById('es-materia')?.value?.trim() || '';

  // Libero = elimina slot esistente
  if (tipo === 'libero') {
    if (slotId) await eliminaSlot();
    else closeModal('edit-slot');
    return;
  }

  try {
    const resp = await API.post('/api/orario', {
      docente_id: docId, giorno, ora, tipo,
      classe_id: classeId ? parseInt(classeId) : null,
      materia
    });
    delete _orarioDocente[docId];
    closeModal('edit-slot');
    if (resp.compresenze_create > 0) {
      showToast(`✓ Slot salvato · ⟳ ${resp.compresenze_create} compresenza/e rilevata/e`, 'success');
    } else {
      showToast('✓ Slot salvato', 'success');
    }
    await renderOrarioPanel(docId);
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

async function eliminaSlot() {
  const slotId = _editCtx?.slotId;
  const docId  = _editCtx?.docId;
  if (!slotId) return;
  try {
    await API.del(`/api/orario/${slotId}`);
    delete _orarioDocente[docId];
    closeModal('edit-slot');
    showToast('Slot rimosso', 'info');
    await renderOrarioPanel(docId);
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

async function svuotaOrario(docId) {
  if (!confirm("Rimuovere tutto l'orario di questo docente?\n\nVerranno rimosse anche le compresenze collegate.")) return;
  try {
    const slots = _orarioDocente[docId] || await API.get(`/api/orario?docente_id=${docId}`);
    for (const s of slots) await API.del(`/api/orario/${s.id}`);
    delete _orarioDocente[docId];
    showToast('Orario svuotato', 'info');
    await renderOrarioPanel(docId);
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

// ─────────────────────────── RICERCA / FILTRI ───────────────────────────

function cercaDocente(query) {
  const q = query.trim().toLowerCase();
  if (!q) { renderDocenti(_allDocenti); return; }
  renderDocenti(_allDocenti.filter(d =>
    (d.cognome + ' ' + d.nome).toLowerCase().includes(q) ||
    (d.materia || '').toLowerCase().includes(q) ||
    (d.ruolo || '').toLowerCase().includes(q)
  ));
}

function filtraRuolo(val) {
  const ruolo = (val === 'Tutti i ruoli') ? '' : val.toLowerCase();
  if (!ruolo) { renderDocenti(_allDocenti); return; }
  renderDocenti(_allDocenti.filter(d => d.ruolo === ruolo));
}

// ─────────────────────────── CRUD DOCENTI ───────────────────────────

function apriNuovoDocente() {
  ['nd-cognome','nd-nome','nd-materia','nd-note'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const ore = document.getElementById('nd-ore');
  if (ore) ore.value = 18;
  const tog = document.getElementById('nd-disp-ecc');
  if (tog) tog.classList.remove('on');
  openModal('nuovo-docente');
}

async function salvaDocente() {
  const cognome = document.getElementById('nd-cognome')?.value?.trim();
  const nome    = document.getElementById('nd-nome')?.value?.trim()    || '';
  const materia = document.getElementById('nd-materia')?.value?.trim() || '';
  const ruolo   = document.getElementById('nd-ruolo')?.value           || 'curriculare';
  const plesso  = document.getElementById('nd-plesso')?.value          || '1';
  const ore     = parseInt(document.getElementById('nd-ore')?.value    || '18');
  const dispEcc = document.getElementById('nd-disp-ecc')?.classList.contains('on') ? 1 : 0;
  const note    = document.getElementById('nd-note')?.value?.trim()    || '';
  if (!cognome) { showToast('Il cognome è obbligatorio', 'error'); return; }
  try {
    await API.post('/api/docenti', { cognome, nome, materia, ruolo,
      plesso_id: parseInt(plesso), ore_cattedra: ore, disp_ore_eccedenti: dispEcc, note });
    closeModal('nuovo-docente');
    showToast(`✓ ${cognome} ${nome} aggiunto`, 'success');
    if (typeof _docentiCache !== 'undefined') _docentiCache = [];
    await loadDocenti();
  } catch(e) { showToast('Errore: ' + e.message, 'error'); }
}

async function eliminaDocente(id, nome) {
  if (!confirm(`Eliminare "${nome}"?\n\nVerranno rimossi anche orario, assenze e compresenze.`)) return;
  try {
    await API.del(`/api/docenti/${id}`);
    if (_docente_aperto === id) _docente_aperto = null;
    delete _orarioDocente[id];
    showToast(`${nome} rimosso`, 'info');
    if (typeof _docentiCache !== 'undefined') _docentiCache = [];
    await loadDocenti();
  } catch(e) { showToast('Errore: ' + e.message, 'error'); }
}

async function eliminaTuttiDocenti() {
  const n = _allDocenti.length;
  if (n === 0) { showToast('Nessun docente da eliminare', 'info'); return; }
  if (!confirm(`⚠ Eliminare TUTTI i ${n} docenti?\n\nQuesta operazione non è reversibile.`)) return;
  try {
    await API.del('/api/docenti');
    _docente_aperto = null;
    _orarioDocente  = {};
    showToast('✓ Tutti i docenti eliminati', 'info');
    if (typeof _docentiCache !== 'undefined') _docentiCache = [];
    await loadDocenti();
  } catch(e) { showToast('Errore: ' + e.message, 'error'); }
}
