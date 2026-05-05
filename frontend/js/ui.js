/* Supplentia v2 – UI helpers */

// ─── STATE ───
let currentDate = new Date();
currentDate.setHours(0,0,0,0);

const GIORNI = ['','Lunedì','Martedì','Mercoledì','Giovedì','Venerdì','Sabato','Domenica'];
const MESI   = ['gennaio','febbraio','marzo','aprile','maggio','giugno','luglio','agosto','settembre','ottobre','novembre','dicembre'];

function isoDate(d) {
  // NON usare toISOString(): converte in UTC e in timezone UTC+1/+2 restituisce il giorno precedente
  return d.getFullYear() + '-'
    + String(d.getMonth() + 1).padStart(2, '0') + '-'
    + String(d.getDate()).padStart(2, '0');
}
function formatDateIT(d) {
  return d.toLocaleDateString('it-IT', {day:'2-digit',month:'2-digit',year:'numeric'});
}
function formatDateLong(d) {
  return `${GIORNI[d.getDay()||7]} ${d.getDate()} ${MESI[d.getMonth()]} ${d.getFullYear()}`;
}
function giornoNum(d) { return d.getDay() === 0 ? 7 : d.getDay(); }

// ─── DATE NAV ───
function changeDate(dir) {
  currentDate.setDate(currentDate.getDate() + dir);
  document.querySelectorAll('#date-display').forEach(el => {
    el.textContent = formatDateIT(currentDate);
  });
  refreshCurrentView();
}
function openDatePicker() {
  const picker = document.getElementById('date-picker');
  if (!picker) return;
  picker.value = isoDate(currentDate);
  picker.click();
}

function setDateFromPicker(val) {
  if (!val) return;
  const [y, m, d] = val.split('-').map(Number);
  currentDate = new Date(y, m - 1, d, 0, 0, 0, 0);
  // Sincronizza tutti i date-display
  document.querySelectorAll('#date-display').forEach(el => {
    el.textContent = formatDateIT(currentDate);
  });
  showView(currentView);
}


function refreshCurrentView() {
  const active = document.querySelector('.nav-item.active');
  if (!active) return;
  const onclick = active.getAttribute('onclick') || '';
  const m = onclick.match(/showView\('(\w+)'\)/);
  if (m) {
    const loaders = {
      dashboard: loadDashboard,
      sostituzioni: loadSostituzioni,
      assenze: loadAssenze,
      storico: loadStorico
    };
    if (loaders[m[1]]) loaders[m[1]]();
  }
}

// ─── NAV ───
const viewMeta = {
  dashboard:    { title: 'Dashboard',              sub: () => `Panoramica giornaliera · ${formatDateLong(currentDate)}` },
  sostituzioni: { title: 'Gestione Sostituzioni',  sub: () => `Assegnazione automatica e manuale · ${formatDateIT(currentDate)}` },
  settimanale:  { title: 'Vista Settimanale',      sub: () => 'Settimana corrente' },
  docenti:      { title: 'Registro Docenti',        sub: () => 'Disponibilità e carico sostituzioni' },
  assenze:      { title: 'Registro Assenze',        sub: () => `Assenze · ${formatDateIT(currentDate)}` },
  compresenze:  { title: 'Compresenze',             sub: () => 'Gestione compresenze da orario' },
  storico:      { title: 'Storico Sostituzioni',    sub: () => 'Log completo con tracciabilità' },
  priorita:     { title: 'Criteri di Priorità',     sub: () => 'Configurazione motore decisionale' },
  reportistica: { title: 'Reportistica',            sub: () => 'Analisi a.s.' },
  impostazioni: { title: 'Impostazioni',            sub: () => 'Configurazione sistema' },
};

let currentView = 'dashboard';  // traccia la vista corrente

function showView(id) {
  currentView = id;
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const view = document.getElementById('view-' + id);
  if (view) view.classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => {
    if ((n.getAttribute('onclick') || '').includes(`'${id}'`)) n.classList.add('active');
  });
  const m = viewMeta[id] || {};
  document.getElementById('topbar-title').textContent = m.title || id;
  document.getElementById('topbar-sub').textContent   = typeof m.sub === 'function' ? m.sub() : (m.sub || '');
  // Carica dati
  const loaders = {
    dashboard: loadDashboard, sostituzioni: loadSostituzioni,
    docenti: loadDocenti, assenze: loadAssenze,
    compresenze: loadCompresenze, storico: loadStorico,
    priorita: loadPriorita, reportistica: loadReportistica,
    uscite: loadUscite,
    impostazioni: loadImpostazioni
  };
  if (loaders[id]) loaders[id]();
}

// ─── MODALS ───
function openModal(id) { document.getElementById('modal-'+id)?.classList.add('open'); }
function closeModal(id) { document.getElementById('modal-'+id)?.classList.remove('open'); }
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) e.target.classList.remove('open');
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
});

// ─── TOAST ───
function showToast(msg, type='info', durata=3000) {
  const colors = { success: 'var(--green)', info: 'var(--accent)', error: 'var(--red)', teal: 'var(--teal)' };
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:24px;right:24px;background:var(--bg2);border:1px solid var(--border2);border-left:3px solid ${colors[type]||colors.info};border-radius:9px;padding:12px 18px;font-size:.83rem;color:var(--text);box-shadow:var(--shadow);z-index:9999;max-width:340px;animation:slideIn .2s ease;font-family:var(--sans)`;
  t.textContent = msg;
  if (!document.getElementById('toast-style')) {
    const s = document.createElement('style');
    s.id = 'toast-style';
    s.textContent = '@keyframes slideIn{from{transform:translateX(20px);opacity:0}to{transform:translateX(0);opacity:1}}';
    document.head.appendChild(s);
  }
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity='0'; t.style.transition='opacity .3s'; setTimeout(()=>t.remove(),300); }, durata);
}

// ─── BADGE HELPERS ───
function causaBadge(tipo) {
  const map = { malattia:'red', permesso:'orange', ferie:'yellow', aggiornamento:'blue', altro:'gray' };
  return `<span class="badge badge-${map[tipo]||'gray'}">${tipo}</span>`;
}
function statoBadge(stato) {
  const map = {
    confermata:         'badge-green',
    attesa:             'badge-yellow',
    bloccata:           'badge-purple',
    annullata:          'badge-gray',
    uscita_anticipata:  'badge-teal',
    entrata_ritardata:  'badge-teal',
  };
  const icons = {
    confermata:         '✓',
    attesa:             '⚠',
    bloccata:           '🔒',
    annullata:          '✕',
    uscita_anticipata:  '⬇',
    entrata_ritardata:  '⬆',
  };
  const labels = {
    confermata:         'Confermata',
    attesa:             'In attesa',
    bloccata:           'Bloccata',
    annullata:          'Annullata',
    uscita_anticipata:  'Uscita anticip.',
    entrata_ritardata:  'Entrata ritard.',
  };
  return `<span class="badge ${map[stato]||'badge-gray'}">${icons[stato]||''} ${labels[stato]||stato}</span>`;
}
function criterioBadge(cid) {
  if (!cid) return '<span style="color:var(--text3)">—</span>';
  const map = {
    compresenza: ['teal','⟳ Compresenza'],
    ore_disp:    ['green','Ore disp.'],
    rec_permessi:['blue','Rec. perm.'],
    stessa_classe:['yellow','Classe'],
    sostegno:    ['purple','Sostegno'],
    ore_eccedenti:   ['orange','Eccedenti'],
    anticipo:        ['teal','⬇ Anticipo'],
    uscita_anticipata:['teal','⬇ Uscita antic.'],
    entrata_ritardata:['teal','⬆ Entrata rit.'],
  };
  const [col, label] = map[cid] || ['gray', cid];
  return `<span class="badge badge-${col}">${label}</span>`;
}

// ─── DRAG & DROP PRIORITY ───
let dragSrc = null;
function dragStart(e) {
  if (e.currentTarget.classList.contains('fixed')) { e.preventDefault(); return; }
  dragSrc = e.currentTarget;
  e.currentTarget.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
}
function dragOver(e) {
  e.preventDefault();
  if (!e.currentTarget.classList.contains('fixed')) {
    e.currentTarget.classList.add('drag-over');
  }
}
function dragLeave(e) { e.currentTarget.classList.remove('drag-over'); }
function dropItem(e) {
  e.preventDefault();
  const target = e.currentTarget;
  target.classList.remove('drag-over');
  if (!dragSrc || dragSrc === target || target.classList.contains('fixed')) return;
  const list = document.getElementById('priority-list');
  const items = [...list.children];
  const srcIdx = items.indexOf(dragSrc);
  const tgtIdx = items.indexOf(target);
  if (srcIdx < tgtIdx) target.after(dragSrc);
  else target.before(dragSrc);
  dragSrc.classList.remove('dragging');
  dragSrc = null;
  updatePriorityNumbers();
}
document.addEventListener('dragend', () => {
  document.querySelectorAll('.priority-item').forEach(el => el.classList.remove('dragging','drag-over'));
});
function updatePriorityNumbers() {
  document.querySelectorAll('#priority-list .priority-num').forEach((el,i) => el.textContent = i+1);
}
