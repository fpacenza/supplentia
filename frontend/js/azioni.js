/* Supplentia v2 – Azioni sostituzioni: assegna manuale + dettaglio */

let _assegnaCtx = null;  // { sostId, classeNome, ora }
let _dettaglioCtx = null; // { sostId }

// ─────────────────────────── ASSEGNA MANUALE ───────────────────────────

async function apriAssegnaManuale(sostId, classeNome, ora) {
  _assegnaCtx = { sostId, classeNome, ora };

  const titolo = document.getElementById('assegna-titolo');
  if (titolo) titolo.textContent = `👤 Assegna – ${classeNome || '?'} · ${ora}ª ora`;

  const nota = document.getElementById('assegna-nota');
  if (nota) nota.value = '';

  const sel = document.getElementById('assegna-docente');
  if (!sel) { openModal('assegna'); return; }

  sel.innerHTML = '<option value="">Caricamento…</option>';
  sel.disabled = true;
  openModal('assegna');  // apre subito il modal, poi popola il select

  try {
    // Calcola il giorno della settimana dalla data corrente
    const d = currentDate;
    const dow = d.getDay();  // 0=dom,1=lun..6=sab
    const giornoNum = dow === 0 ? 7 : dow;  // converti: dom=7,lun=1..sab=6
    const dataStr = isoDate(currentDate);

    // UNA SOLA chiamata API: ottiene tutti i docenti con stato disponibilità
    const docs = await API.get(
      `/api/disponibili?data=${dataStr}&giorno=${giornoNum}&ora=${ora}`
    );

    const disponibili = docs.filter(d => d.stato_disponibilita === 'disponibile');
    const conLezione  = docs.filter(d => d.stato_disponibilita === 'lezione');
    const occupati    = docs.filter(d => d.stato_disponibilita === 'occupato');
    const assenti     = docs.filter(d => d.stato_disponibilita === 'assente');

    const fmtDoc = d => {
      const nome  = `${d.cognome} ${d.nome}`.trim();
      const mat   = d.materia ? ` – ${d.materia}` : '';
      const ecc   = d.ore_eccedenti_usate > 0 ? ` [${d.ore_eccedenti_usate} ecc.]` : '';
      return `${nome}${mat}${ecc}`;
    };

    sel.innerHTML =
      '<option value="">Seleziona docente…</option>' +

      (disponibili.length
        ? `<optgroup label="✓ Liberi (${disponibili.length})">`
          + disponibili.map(d =>
              `<option value="${d.id}">${fmtDoc(d)}</option>`
            ).join('') + '</optgroup>'
        : '') +

      (conLezione.length
        ? `<optgroup label="📖 Con lezione propria (${conLezione.length})">`
          + conLezione.map(d =>
              `<option value="${d.id}">${fmtDoc(d)} (ha lezione)</option>`
            ).join('') + '</optgroup>'
        : '') +

      (occupati.length
        ? `<optgroup label="⚠ Già assegnati come sostituti (${occupati.length})">`
          + occupati.map(d =>
              `<option value="${d.id}">${fmtDoc(d)} (già assegnato)</option>`
            ).join('') + '</optgroup>'
        : '') +

      (assenti.length
        ? `<optgroup label="✕ Assenti (${assenti.length})" disabled>`
          + assenti.map(d =>
              `<option value="${d.id}" disabled>${fmtDoc(d)} (assente)</option>`
            ).join('') + '</optgroup>'
        : '');

    sel.disabled = false;

  } catch(e) {
    sel.innerHTML = '<option value="">Errore caricamento – ' + e.message + '</option>';
    sel.disabled = false;
  }
}

async function confermaAssegnaManuale() {
  if (!_assegnaCtx) return;
  const { sostId } = _assegnaCtx;

  const sel  = document.getElementById('assegna-docente');
  const nota = document.getElementById('assegna-nota');
  const docId = sel?.value;
  const motivazione = nota?.value?.trim() || 'Assegnazione manuale';

  if (!docId) { showToast('Seleziona un docente', 'error'); return; }

  try {
    await API.put(`/api/sostituzioni/${sostId}`, {
      docente_sostituto_id: parseInt(docId),
      stato:       'confermata',
      tipo:        'manuale',
      bloccata:    1,
      motivazione
    });
    closeModal('assegna');
    showToast('✓ Sostituzione manuale confermata e bloccata', 'success');
    // Ricarica la vista corrente
    if (currentView === 'dashboard') loadDashboard();
    else if (currentView === 'sostituzioni') loadSostituzioni();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

// ─────────────────────────── DETTAGLIO ───────────────────────────

async function apriDettaglio(sostId) {
  _dettaglioCtx = { sostId };
  const content = document.getElementById('dettaglio-content');
  if (!content) { return; }
  content.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  openModal('dettaglio');

  try {
    const sostituzioni = await API.get(`/api/sostituzioni?data=${isoDate(currentDate)}`);
    const s = sostituzioni.find(x => x.id === sostId);
    if (!s) { content.innerHTML = 'Sostituzione non trovata.'; return; }

    const GIORNI = ['','Lunedì','Martedì','Mercoledì','Giovedì','Venerdì','Sabato'];
    const giorno = GIORNI[new Date(isoDate(currentDate)).getDay() === 0 ? 7 : new Date(isoDate(currentDate)).getDay()];

    content.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:.85rem">
        <tr><td style="color:var(--text3);padding:4px 8px 4px 0;width:120px">Data</td>
            <td style="padding:4px 0"><strong>${formatDateLong(currentDate)}</strong></td></tr>
        <tr><td style="color:var(--text3);padding:4px 8px 4px 0">Ora</td>
            <td>${s.ora}ª ora</td></tr>
        <tr><td style="color:var(--text3);padding:4px 8px 4px 0">Classe</td>
            <td>${s.classe_nome || '—'}</td></tr>
        <tr><td style="color:var(--text3);padding:4px 8px 4px 0">Assente</td>
            <td>${s.assente_nome}</td></tr>
        <tr><td style="color:var(--text3);padding:4px 8px 4px 0">Sostituto</td>
            <td><strong>${s.sostituto_nome || '— non assegnato —'}</strong></td></tr>
        <tr><td style="color:var(--text3);padding:4px 8px 4px 0">Criterio</td>
            <td>${criterioBadge(s.criterio_id)}</td></tr>
        <tr><td style="color:var(--text3);padding:4px 8px 4px 0">Stato</td>
            <td>${statoBadge(s.stato)} ${s.bloccata ? '🔒' : ''}</td></tr>
        <tr><td style="color:var(--text3);padding:4px 8px 4px 0">Motivazione</td>
            <td style="font-size:.8rem;color:var(--text2)">${s.motivazione || '—'}</td></tr>
        <tr><td style="color:var(--text3);padding:4px 8px 4px 0">Punteggio</td>
            <td>${s.punteggio || 0} pt</td></tr>
      </table>`;

    // Pulsanti: Annulla sempre visibile se non già annullata;
    // Modifica/Riassegna visibile se ha sostituto assegnato
    const btnAnnulla = document.getElementById('dettaglio-btn-annulla');
    if (btnAnnulla) btnAnnulla.style.display =
      !['annullata','uscita_anticipata','entrata_ritardata'].includes(s.stato) ? 'inline-flex' : 'none';

    const btnModifica = document.getElementById('dettaglio-btn-modifica');
    if (btnModifica) {
      const mostraModifica = s.stato === 'confermata' || s.stato === 'anticipo';
      btnModifica.style.display = mostraModifica ? 'inline-flex' : 'none';
      btnModifica.onclick = () => {
        closeModal('dettaglio');
        apriAssegnaManuale(s.id, s.classe_nome, s.ora);
      };
    }

  } catch(e) {
    content.innerHTML = `<span style="color:var(--red)">Errore: ${e.message}</span>`;
  }
}

async function annullaDaDettaglio() {
  if (!_dettaglioCtx) return;
  const { sostId } = _dettaglioCtx;
  try {
    // DELETE: riporta ad 'attesa' e riesegue il motore
    await API.del(`/api/sostituzioni/${sostId}`);
    closeModal('dettaglio');
    showToast('Sostituzione rimossa – slot riportato in attesa e ricalcolato', 'info');
    if (currentView === 'dashboard') loadDashboard();
    else if (currentView === 'sostituzioni') loadSostituzioni();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}
