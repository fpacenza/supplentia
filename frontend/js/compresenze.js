/* Supplentia – Compresenze */
const GIORNI_LABELS = ['','Lunedì','Martedì','Mercoledì','Giovedì','Venerdì'];

async function loadCompresenze() {
  const container = document.getElementById('comp-list');
  if (!container) return;
  container.innerHTML = '<div class="loading"><div class="spinner"></div>Caricamento…</div>';
  try {
    const rows = await API.get('/api/compresenze');
    if (rows.length === 0) {
      container.innerHTML = '<div style="color:var(--text3);padding:16px;text-align:center">Nessuna compresenza configurata.<br>Aggiungi le compresenze dall\'orario per abilitare il criterio P0.</div>';
      return;
    }
    container.innerHTML = rows.map(c => `
      <div class="comp-row">
        <span class="comp-badge">P0 ⟳</span>
        <div style="flex:0;min-width:90px">
          <div style="font-family:var(--mono);font-size:.78rem;color:var(--accent2)">${GIORNI_LABELS[c.giorno]||c.giorno} – ${c.ora}ª ora</div>
        </div>
        <div style="flex:0;min-width:70px">
          <span class="badge badge-blue">${c.classe_nome}</span>
        </div>
        <div style="flex:1;font-size:.83rem">
          <strong>${c.doc1_nome}</strong> <span style="color:var(--text3)">⟷</span> <strong>${c.doc2_nome}</strong>
          ${c.note ? `<span style="color:var(--text3);font-size:.72rem;margin-left:8px">${c.note}</span>` : ''}
        </div>
        <button class="btn btn-danger btn-sm">✕</button>
      </div>`).join('');
  } catch(e) {
    container.innerHTML = '<div style="color:var(--red);padding:16px">Errore: ' + e.message + '</div>';
  }
}
