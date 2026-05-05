/* Supplentia v2 – Impostazioni */
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
    if (tagline) tagline.textContent = `v2.0 · ${cfg.scuola?.nome||''}`;
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
    if (tagline) tagline.textContent = `v2.0 · ${payload.scuola.nome}`;
  } catch(e) {
    showToast('Errore: ' + e.message, 'error');
  }
}
