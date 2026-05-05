/* SubstManager v2 – Storico */
async function loadStorico() {
  const tbody = document.getElementById('storico-table');
  if (!tbody) return;
  const da = document.getElementById('storico-da')?.value || '2026-01-01';
  const a  = document.getElementById('storico-a')?.value  || isoDate(currentDate);
  tbody.innerHTML = '<tr><td colspan="8"><div class="loading"><div class="spinner"></div>Caricamento…</div></td></tr>';
  try {
    const rows = await API.get(`/api/storico?da=${da}&a=${a}`);
    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="color:var(--text3);text-align:center;padding:20px">Nessun record nel periodo selezionato</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(s => `
      <tr>
        <td><span class="badge badge-gray" style="font-family:var(--mono)">${s.data}</span></td>
        <td><div class="ora-badge">${s.ora}ª</div></td>
        <td><div class="td-name">${s.classe_nome||'—'}</div></td>
        <td><div class="td-name">${s.assente_nome}</div></td>
        <td>${s.sostituto_nome ? `<div class="td-name">${s.sostituto_nome}</div>` : '<span style="color:var(--text3)">—</span>'}</td>
        <td>${criterioBadge(s.criterio_id)}</td>
        <td>${statoBadge(s.stato)}</td>
        <td><span style="font-size:.7rem;color:var(--text3);font-family:var(--mono)">${s.punteggio>0?s.punteggio+'/100':'—'}</span></td>
      </tr>`).join('');
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="8" style="color:var(--red)">Errore: ' + e.message + '</td></tr>';
  }
}
