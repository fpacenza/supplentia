/* Supplentia v2 – Reportistica */
async function loadReportistica() {
  const container = document.getElementById('report-docenti');
  if (!container) return;
  try {
    const rows = await API.get('/api/report/docenti');
    const max = rows[0]?.tot_sostituzioni || 1;
    container.innerHTML = rows.map(r => `
      <div class="bar-row">
        <div class="bar-label">${r.nome}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.round(r.tot_sostituzioni/max*100)}%;background:var(--accent)"></div></div>
        <div class="bar-val">${r.tot_sostituzioni}</div>
      </div>`).join('');
  } catch(e) {
    container.innerHTML = '<div style="color:var(--red)">Errore: ' + e.message + '</div>';
  }

  // Carica anche riepilogo ore eccedenti
  const contEcc = document.getElementById('report-ore-eccedenti');
  if (!contEcc) return;
  try {
    const ecc = await API.get('/api/ore_eccedenti');
    if (!ecc.length) {
      contEcc.innerHTML = '<div style="color:var(--text3);font-size:.85rem">Nessuna ora eccedente registrata questa settimana.</div>';
      return;
    }
    const maxEcc = Math.max(...ecc.map(r => r.ore_totale), 1);
    contEcc.innerHTML = `
      <div style="font-size:.75rem;color:var(--text3);margin-bottom:10px">
        Settimana ${ecc[0]?.settimana || ''}
        <span style="float:right;color:var(--text2)">Sett. / Totale</span>
      </div>` +
      ecc.filter(r => r.ore_totale > 0).map(r => `
      <div class="bar-row">
        <div class="bar-label">${r.cognome} ${r.nome}</div>
        <div class="bar-track">
          <div class="bar-fill" style="width:${Math.round(r.ore_totale/maxEcc*100)}%;background:var(--teal)"></div>
        </div>
        <div class="bar-val" style="min-width:60px;text-align:right">
          <span style="color:var(--accent);font-weight:600">${r.ore_settimana}</span>
          <span style="color:var(--text3)"> / ${r.ore_totale}</span>
        </div>
      </div>`).join('') ||
      '<div style="color:var(--text3);font-size:.85rem">Nessuna ora eccedente registrata.</div>';
  } catch(e) {
    contEcc.innerHTML = '<div style="color:var(--red)">Errore: ' + e.message + '</div>';
  }
}
