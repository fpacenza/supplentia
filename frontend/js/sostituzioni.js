/* Supplentia – Sostituzioni */

async function loadSostituzioni() {
  const data = isoDate(currentDate);
  const tbody = document.getElementById('sost-table');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="9"><div class="loading"><div class="spinner"></div>Caricamento…</div></td></tr>';
  try {
    const rows = await API.get(`/api/sostituzioni?data=${data}`);
    const rowsVisibili = rows.filter(s => s.stato !== 'annullata');
    if (rowsVisibili.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" style="color:var(--text3);text-align:center;padding:20px">Nessuna sostituzione per questa data</td></tr>';
      return;
    }
    tbody.innerHTML = rowsVisibili.map(s => {
      const compTag = s.criterio_id === 'compresenza'
        ? ' <span class="badge badge-teal" style="font-size:.6rem">⟳ COMP</span>' : '';
      const bloccataChk = `
        <label class="blocca-label" title="${s.bloccata ? 'Bloccata: esclusa dal ricalcolo automatico' : 'Clicca per bloccare questa sostituzione'}">
          <input type="checkbox" class="blocca-chk" ${s.bloccata ? 'checked' : ''}
            onchange="toggleBlocca(${s.id}, this.checked)">
          <span class="blocca-ico">${s.bloccata ? '🔒' : '🔓'}</span>
        </label>`;
      return `<tr class="${s.bloccata ? 'row-bloccata' : ''}">
        <td><div class="ora-badge">${s.ora}ª</div></td>
        <td><div class="td-name">${s.classe_nome||'—'}</div></td>
        <td><div class="td-name">${s.assente_nome}</div></td>
        <td>${causaBadge(s.tipo||'altro')}</td>
        <td>${s.sostituto_nome ? `<div class="td-name">${s.sostituto_nome}${compTag}</div><div class="td-sub">${s.motivazione||''}</div>` : '<span style="color:var(--text3);font-size:.78rem">— non assegnata —</span>'}</td>
        <td>${criterioBadge(s.criterio_id)}</td>
        <td><span class="badge badge-${s.tipo==='manuale'?'purple':'blue'}">${s.tipo==='manuale'?'🔒 Manuale':'Auto'}</span></td>
        <td>${statoBadge(s.stato)}</td>
        <td>${bloccataChk}</td>
        <td>
          <div style="display:flex;gap:4px">
            ${s.stato==='attesa' ? `<button class="btn btn-primary btn-sm" onclick="apriAssegnaManuale(${s.id},'${(s.classe_nome||'').replace(/'/g,'')}',${s.ora})">Assegna</button>` : `<button class="btn btn-secondary btn-sm" onclick="apriDettaglio(${s.id})">···</button>`}
            <button class="btn btn-danger btn-sm" onclick="annullaSostituzione(${s.id}, this)" title="Annulla sostituzione">✕</button>
          </div>
        </td>
      </tr>`;
    }).join('');

    // Aggiorna badge header
    const coperte = rows.filter(r=>r.stato==='confermata').length;
    const el = document.getElementById('sost-badge');
    if (el) el.textContent = `${coperte} / ${rows.length} coperte`;

    // Alert
    const alertEl = document.getElementById('sost-alert');
    if (alertEl) {
      const nCoperte = rows.filter(r=>r.stato==='attesa').length;
      alertEl.style.display = nCoperte > 0 ? 'flex' : 'none';
      if (nCoperte > 0) alertEl.textContent = `⚠ ${nCoperte} sostituzione/i non coperta/e. Valutare assegnazione manuale.`;
    }
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="9" style="color:var(--red)">Errore: ' + e.message + '</td></tr>';
  }
}

async function annullaSostituzione(id, btn) {
  if (!confirm('Rimuovere questa sostituzione?\nLo slot verrà riportato in attesa e il motore tenterà di ricoprirlo.')) return;
  try {
    await API.del(`/api/sostituzioni/${id}`);
    showToast('Sostituzione rimossa · Slot ricalcolato', 'info');
    loadSostituzioni();
    if (typeof currentView !== 'undefined' && currentView === 'dashboard') loadDashboard();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

async function toggleBlocca(sostId, bloccata) {
  try {
    await API.put(`/api/sostituzioni/${sostId}`, { bloccata: bloccata ? 1 : 0 });
    showToast(bloccata ? '🔒 Sostituzione bloccata – esclusa dal ricalcolo' : '🔓 Sostituzione sbloccata', 'info');
    // Aggiorna l'icona e la classe riga senza ricaricare tutto
    const chk = document.querySelector(`.blocca-chk[onchange*="${sostId}"]`);
    if (chk) {
      const ico = chk.parentElement.querySelector('.blocca-ico');
      if (ico) ico.textContent = bloccata ? '🔒' : '🔓';
      const label = chk.closest('label');
      if (label) label.title = bloccata ? 'Bloccata: esclusa dal ricalcolo automatico' : 'Clicca per bloccare questa sostituzione';
      const tr = chk.closest('tr');
      if (tr) tr.className = bloccata ? 'row-bloccata' : '';
    }
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
    // Ripristina la checkbox in caso di errore
    const chk = document.querySelector(`.blocca-chk[onchange*="${sostId}"]`);
    if (chk) chk.checked = !bloccata;
  }
}
