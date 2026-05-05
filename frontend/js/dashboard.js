/* SubstManager v2 – Dashboard */

async function loadDashboard() {
  const data = isoDate(currentDate);
  try {
    const [sostituzioni, assenze] = await Promise.all([
      API.get(`/api/sostituzioni?data=${data}`),
      API.get(`/api/assenze?data=${data}`)
    ]);

    const STATI_RISOLTI = ['confermata', 'uscita_anticipata', 'entrata_ritardata'];
    const coperte   = sostituzioni.filter(s => STATI_RISOLTI.includes(s.stato)).length;
    const attesa    = sostituzioni.filter(s => s.stato === 'attesa').length;
    const totSlot   = sostituzioni.length;
    const perc      = totSlot > 0 ? Math.round(coperte/totSlot*100) : 0;

    document.getElementById('dash-assenze-val').textContent = assenze.length;
    document.getElementById('dash-coperte-val').textContent = coperte;
    document.getElementById('dash-attesa-val').textContent  = attesa;
    document.getElementById('dash-perc-sub').textContent    = `${perc}% copertura`;

    // Tabella sostituzioni odierne
    const tbody = document.getElementById('dash-table');
    if (!tbody) return;
    if (sostituzioni.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text3);text-align:center;padding:20px">Nessuna sostituzione per questa data</td></tr>';
      return;
    }
    const sostVisibili = sostituzioni.filter(s => s.stato !== 'annullata');
    if (sostVisibili.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text3);text-align:center;padding:20px">Nessuna sostituzione per questa data</td></tr>';
      return;
    }
    tbody.innerHTML = sostVisibili.map(s => `
      <tr>
        <td><div class="ora-badge">${s.ora}ª</div></td>
        <td><div class="td-name">${s.classe_nome||'—'}</div></td>
        <td><div class="td-name">${s.assente_nome}</div></td>
        <td>${
          s.stato === 'uscita_anticipata'  ? '<span style="color:var(--teal);font-size:.78rem">⬇ Classe esce prima</span>' :
          s.stato === 'entrata_ritardata'  ? '<span style="color:var(--teal);font-size:.78rem">⬆ Classe entra tardi</span>' :
          s.tipo  === 'anticipo'           ? `<div class="td-name">${s.sostituto_nome||'—'} <span style="color:var(--teal);font-size:.7rem">(anticipa)</span></div>` :
          s.sostituto_nome                 ? `<div class="td-name">${s.sostituto_nome}</div>` :
                                             '<span style="color:var(--text3);font-size:.78rem">— non assegnata —</span>'
        }</td>
        <td>${criterioBadge(s.criterio_id)}</td>
        <td>${statoBadge(s.stato)}</td>
        <td>
          <div style="display:flex;gap:4px">
            ${s.stato === 'attesa' ? `<button class="btn btn-primary btn-sm" onclick="apriAssegnaManuale(${s.id},'${(s.classe_nome||'').replace(/'/g,String.fromCharCode(39))}',${s.ora})">Assegna</button>` : ''}
            <button class="btn btn-secondary btn-sm" onclick="apriDettaglio(${s.id})" title="Dettaglio / Annulla">···</button>
          </div>
        </td>
      </tr>`).join('');

    // Alert
    const alertEl = document.getElementById('dash-alert');
    if (alertEl) {
      if (attesa > 0) {
        alertEl.style.display='flex';
        alertEl.textContent = `⚠ ${attesa} sostituzione/i non ancora assegnata/e per ${formatDateIT(currentDate)}.`;
      } else {
        alertEl.style.display='none';
      }
    }
  } catch(e) {
    console.error(e);
    showToast('Errore caricamento dashboard', 'error');
  }
}

async function runEngine(forza = false) {
  if (forza) {
    if (!confirm('Ricalcolare da zero tutte le sostituzioni di questa data?\n\nLe sostituzioni già confermate (non bloccate) verranno sostituite con quelle ricalcolate.')) return;
  }
  showToast(forza ? 'Ricalcolo forzato in corso…' : 'Motore in esecuzione…', 'info');
  try {
    const result = await API.post('/api/engine/run', {
      data: isoDate(currentDate),
      forza_ricalcolo: forza
    });
    const msg = forza
      ? `✓ Ricalcolo completato: ${result.coperte}/${result.slot_totali} assegnate (${result.percentuale}%)`
      : `✓ ${result.coperte}/${result.slot_totali} sostituzioni assegnate (${result.percentuale}%)`;
    showToast(msg, 'success');
    loadDashboard();
    if (document.getElementById('view-sostituzioni')?.classList.contains('active')) {
      loadSostituzioni();
    }
  } catch(e) {
    showToast('Errore motore: ' + e.message, 'error');
  }
}
