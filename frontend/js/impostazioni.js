/* Supplentia – Impostazioni */
async function loadImpostazioni() {
  try {
    const cfg = await API.get('/api/config');
    // Scuola
    const fields = {
      'imp-nome':    cfg.scuola?.nome,
      'imp-anno':    cfg.scuola?.anno_scolastico,
      'imp-citta':   cfg.scuola?.citta,
      'imp-dirigente': cfg.scuola?.dirigente,
      'imp-vicepreside': cfg.scuola?.vicepreside,
      'imp-ore-gg':  cfg.orario?.ore_giornaliere,
      'imp-giorni':  cfg.orario?.giorni_settimana,
      'imp-max-ecc': cfg.engine?.max_ore_eccedenti_settimana,
      'imp-porta':   cfg.sistema?.porta,
    };
    for (const [id, val] of Object.entries(fields)) {
      const el = document.getElementById(id);
      if (el && val !== undefined) el.value = val;
    }
    // Toggles notifiche
    const togMap = {
      'tog-non-coperte': cfg.notifiche?.avviso_non_coperte,
      'tog-email-gg':    cfg.notifiche?.email_giornaliera,
      'tog-limite-ore':  cfg.notifiche?.avviso_limite_ore,
      'tog-report-sett': cfg.notifiche?.report_settimanale,
    };
    for (const [id, val] of Object.entries(togMap)) {
      const el = document.getElementById(id);
      if (el) el.classList.toggle('on', !!val);
    }
    // Aggiorna tagline sidebar
    const tagline = document.querySelector('.sidebar-logo .tagline');
    if (tagline) tagline.textContent = `${cfg.scuola?.nome||''}`;
  } catch(e) {
    showToast('Errore caricamento impostazioni: ' + e.message, 'error');
  }
}

async function saveImpostazioni() {
  const payload = {
    scuola: {
      nome:             document.getElementById('imp-nome')?.value,
      anno_scolastico:  document.getElementById('imp-anno')?.value,
      citta:            document.getElementById('imp-citta')?.value,
      dirigente:        document.getElementById('imp-dirigente')?.value,
      vicepreside:      document.getElementById('imp-vicepreside')?.value,
    },
    orario: {
      ore_giornaliere:  parseInt(document.getElementById('imp-ore-gg')?.value||6),
      giorni_settimana: parseInt(document.getElementById('imp-giorni')?.value||5),
    },
    engine: {
      max_ore_eccedenti_settimana: parseInt(document.getElementById('imp-max-ecc')?.value||6),
    },
    notifiche: {
      avviso_non_coperte: document.getElementById('tog-non-coperte')?.classList.contains('on'),
      email_giornaliera:  document.getElementById('tog-email-gg')?.classList.contains('on'),
      avviso_limite_ore:  document.getElementById('tog-limite-ore')?.classList.contains('on'),
      report_settimanale: document.getElementById('tog-report-sett')?.classList.contains('on'),
    },
    sistema: {
      porta: parseInt(document.getElementById('imp-porta')?.value||8080),
    }
  };
  try {
    await API.post('/api/config', payload);
    showToast('Impostazioni salvate', 'success');
    // Aggiorna nome sidebar
    const tagline = document.querySelector('.sidebar-logo .tagline');
    if (tagline) tagline.textContent = `${payload.scuola.nome}`;
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}


// ─────────────────────────── GESTIONE UTENTI ───────────────────────────

const PERM_LABEL = {
  admin:     '👑 Admin',
  scrittura: '✏ Lettura + Scrittura',
  lettura:   '👁 Solo lettura',
  // retrocompatibilità vecchi ruoli
  vicepreside: '✏ Lettura + Scrittura',
  operatore:   '✏ Lettura + Scrittura',
  segreteria:  '👁 Solo lettura',
  dirigente:   '👁 Solo lettura',
};
const PERM_BADGE = {
  admin:       'badge-red',
  scrittura:   'badge-blue',
  lettura:     'badge-gray',
  vicepreside: 'badge-blue',
  operatore:   'badge-blue',
  segreteria:  'badge-gray',
  dirigente:   'badge-gray',
};

let _meId = null;  // id dell'utente loggato

async function loadUtenti() {
  const container = document.getElementById('utenti-list');
  if (!container) return;

  container.innerHTML = '<div class="loading"><div class="spinner"></div>Caricamento…</div>';

  try {
    const [utenti, me] = await Promise.all([
      API.get('/api/utenti'),
      API.get('/api/me')
    ]);
    _meId = me.id;

    container.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:.83rem">
        <thead><tr style="border-bottom:2px solid var(--border)">
          <th style="text-align:left;padding:6px 10px;color:var(--text3);font-weight:500;width:140px">Username</th>
          <th style="text-align:left;padding:6px 10px;color:var(--text3);font-weight:500">Nome</th>
          <th style="text-align:left;padding:6px 10px;color:var(--text3);font-weight:500;width:180px">Permessi</th>
          <th style="padding:6px 10px;width:140px"></th>
        </tr></thead>
        <tbody>
          ${utenti.map(u => {
            const isSelf = u.id == _meId;
            const label  = PERM_LABEL[u.ruolo] || u.ruolo;
            const badge  = PERM_BADGE[u.ruolo] || 'badge-gray';
            const disab  = !u.attivo ? ' style="opacity:.5"' : '';
            return `<tr style="border-top:1px solid var(--border)"${disab}>
              <td style="padding:8px 10px">
                <code style="font-family:var(--mono);font-size:.8rem">${u.username}</code>
                ${isSelf ? ' <span style="color:var(--accent);font-size:.7rem">(tu)</span>' : ''}
                ${!u.attivo ? ' <span style="color:var(--red);font-size:.7rem">disabilitato</span>' : ''}
              </td>
              <td style="padding:8px 10px">${u.nome}</td>
              <td style="padding:8px 10px"><span class="badge ${badge}" style="font-size:.72rem">${label}</span></td>
              <td style="padding:8px 10px;text-align:right">
                <div style="display:flex;gap:5px;justify-content:flex-end">
                  <button class="btn btn-secondary btn-sm" onclick="apriCambioPwd(${u.id})" title="Cambia password">🔑</button>
                  ${!isSelf ? `
                    <button class="btn btn-secondary btn-sm" onclick="togglePerm(${u.id},'${u.ruolo}')" title="Cambia permessi">
                      ${u.ruolo === 'lettura' || u.ruolo === 'segreteria' || u.ruolo === 'dirigente' ? '⬆ Scrittura' : '⬇ Lettura'}
                    </button>
                    <button class="btn btn-${u.attivo ? 'secondary' : 'primary'} btn-sm" onclick="toggleAttivo(${u.id},${u.attivo?0:1})">
                      ${u.attivo ? 'Disabilita' : 'Abilita'}
                    </button>
                    <button class="btn btn-danger btn-sm" onclick="eliminaUtente(${u.id},'${u.username}')">✕</button>
                  ` : ''}
                </div>
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  } catch(e) {
    container.innerHTML = `<div style="color:var(--red)">Errore: ${e.message}</div>`;
  }
}

function apriNuovoUtente() {
  document.getElementById('nu-username').value = '';
  document.getElementById('nu-nome').value = '';
  document.getElementById('nu-password').value = '';
  // Seleziona "scrittura" di default
  const r = document.getElementById('nu-perm-scrittura');
  if (r) r.checked = true;
  document.getElementById('nu-titolo').textContent = '👤 Nuovo Utente';
  openModal('nuovo-utente');
}

async function salvaUtente() {
  const username = document.getElementById('nu-username')?.value?.trim();
  const nome     = document.getElementById('nu-nome')?.value?.trim() || username;
  const password = document.getElementById('nu-password')?.value || '';
  const ruolo    = document.querySelector('input[name="nu-ruolo"]:checked')?.value || 'scrittura';

  if (!username) { showToast('Username obbligatorio', 'error'); return; }

  try {
    await API.post('/api/utenti', { _action:'create', username, nome, ruolo,
                                    password: password || username });
    closeModal('nuovo-utente');
    showToast(`✓ Utente "${username}" creato · permessi: ${PERM_LABEL[ruolo]}`, 'success', 5000);
    await loadUtenti();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

async function togglePerm(id, ruoloAttuale) {
  // Alterna tra lettura e scrittura
  const isLettura = ['lettura','segreteria','dirigente'].includes(ruoloAttuale);
  const nuovoRuolo = isLettura ? 'scrittura' : 'lettura';
  try {
    await API.put(`/api/utenti/${id}`, { ruolo: nuovoRuolo });
    showToast(`Permessi aggiornati: ${PERM_LABEL[nuovoRuolo]}`, 'info');
    await loadUtenti();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

async function toggleAttivo(id, nuovoStato) {
  try {
    await API.put(`/api/utenti/${id}`, { attivo: nuovoStato });
    showToast(nuovoStato ? 'Utente abilitato' : 'Utente disabilitato', 'info');
    await loadUtenti();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

async function eliminaUtente(id, username) {
  if (!confirm(`Eliminare definitivamente l'utente "${username}"?`)) return;
  try {
    await API.del(`/api/utenti/${id}`);
    showToast(`Utente "${username}" eliminato`, 'info');
    await loadUtenti();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}

// ─── Cambio password (aperto dal pulsante 🔑 nella lista utenti) ───
let _cambioPasswordTargetId = null;

function apriCambioPwd(id) {
  _cambioPasswordTargetId = id;
  document.getElementById('cp-nuova').value = '';
  document.getElementById('cp-conferma').value = '';
  openModal('cambio-pwd');
}

async function modificaPassword(id, username) {
  apriCambioPwd(id);
}

async function confermaCambioPassword() {
  const nuova    = document.getElementById('cp-nuova')?.value;
  const conferma = document.getElementById('cp-conferma')?.value;
  if (!nuova)           { showToast('Inserisci la nuova password', 'error'); return; }
  if (nuova !== conferma){ showToast('Le password non coincidono', 'error'); return; }
  if (nuova.length < 4) { showToast('Password troppo corta (min 4 caratteri)', 'error'); return; }

  let targetId = _cambioPasswordTargetId;
  if (!targetId) {
    try { const me = await API.get('/api/me'); targetId = me.id; }
    catch(e) { showToast('Errore: ' + e.message, 'error'); return; }
  }

  try {
    await API.put(`/api/utenti/${targetId}`, { password: nuova });
    closeModal('cambio-pwd');
    _cambioPasswordTargetId = null;
    showToast('✓ Password aggiornata', 'success');
    if (typeof loadUtenti === 'function') loadUtenti();
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}
