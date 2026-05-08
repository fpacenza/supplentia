#!/usr/bin/env python3
"""
Supplentia – Importa Orario da PDF Classi
Usa pdfplumber – nessun tool esterno necessario.

Uso:
  python3 scripts/importa_orario.py --classi timbro_CLASSI_dal_09_12_25.pdf
"""

import os, sys, re, sqlite3, argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, 'data', 'supplentia.db')

try:
    import pdfplumber
except ImportError:
    print("❌ Manca pdfplumber. Installa con:\n   pip install pdfplumber")
    sys.exit(1)

# ─────────────────────────── COSTANTI ───────────────────────────

GIORNI_KEYS = ['LUNEDÌ','MARTEDÌ','MERCOLEDÌ','GIOVEDÌ','VENERDÌ','SABATO',
               'LUNEDI','MARTEDI','MERCOLEDI','GIOVEDI','VENERDI']
GIORNO_NUM  = {k:v for k,v in [
    ('LUNEDÌ',1),('LUNEDI',1),('MARTEDÌ',2),('MARTEDI',2),
    ('MERCOLEDÌ',3),('MERCOLEDI',3),('GIOVEDÌ',4),('GIOVEDI',4),
    ('VENERDÌ',5),('VENERDI',5),('SABATO',6)
]}
ORA_LABELS  = {'08:00':1,'09:00':2,'10:00':3,'11:00':4,'12:00':5,'13:00':6}
SKIP_GLOBAL = {'ITTS','"E.','SCALFARO"','SCALFARO','Torna','alto','---','in'} | set(GIORNI_KEYS)

# Parole che NON sono cognomi docenti
NON_COGNOMI = {
    'ITALIANO','STORIA','MATEMATICA','INGLESE','FISICA','CHIMICA',
    'TECNOLOGIA','TECNOLOGIE','INFORMATICHE','GRAFICA','RELIGIONE',
    'MOTORIE','DIRITTO','ECONOMIA','BIOLO','TERRA','GEOGRAFIA','GEOGRAFFIA',
    'SISTEMI','AUTOMATICI','MECCANICA','MECCANICHE','AUTOMAZIONE','INFORMATICA',
    'LABORATORI','TECNICI','TEORIA','RETI','TELECOMUNICAZIONI','SALA','DOCENTI','PALESTRA',
    'S.T.A.','D.P.O.','T.P.S.I.T.','T.P.S.E.E.','G.P.O.I.',
    'COMPL.','COMUNIC.','MULTIMED.','ELETTROT.','ELETTRON.',
    'ORG.','GEST.','TEC.','PROC.','PROD.','PROG.','INT.','SC.',
    # Iniziali nome (appaiono con cognomi: ROCCA FE., AIELLO C., OCCHIUTO F.S.)
    'FE.','FR.','A.NIO','A.TTA','G.CO','G.PPE','M.C.','F.S.',
    'C.','D.','G.','L.','V.','A.','R.','S.','M.',
    # Codici indirizzo
    '(EL)','(ET)','(I)','(T)',
}

def is_aula(s):
    return bool(re.match(
        r'^(S\d{1,2}|\d{1,2}|AP[12]|PALESTRA|SD.*|CIRIMELE|[A-Z]{1,2}\d+|\d+[A-Z]*)$',
        s.strip()
    ))

def is_cognome(s):
    s2 = s.rstrip(',').rstrip('.')
    if len(s2) < 4: return False
    if not s2.replace("'", "").isupper(): return False
    if re.search(r'\d', s2): return False
    if s2 in NON_COGNOMI or s in NON_COGNOMI: return False
    if is_aula(s2): return False
    if re.match(r'^[\(\)\.\-\s]+$', s2): return False
    if re.match(r'^[A-Z]\.[A-Z]+\.?$', s2): return False  # "A.NIO", "F.S."
    if re.match(r'^\([A-Z]+\)$', s2): return False         # "(EL)"
    return True

# ─────────────────────────── PARSER ───────────────────────────

def _get_docenti(words, gx_s, gx_e, y_start, y_end):
    """Estrae cognomi docenti dalle parole nell'area (gx, gy) specificata."""
    ww = [w for w in words
          if gx_s <= w['x0'] <= gx_e
          and y_start <= w['top'] <= y_end
          and w['text'] not in SKIP_GLOBAL
          and w['text'] not in ORA_LABELS
          and w['text'] != '---']
    return list(dict.fromkeys(
        w['text'].rstrip(',') for w in ww
        if is_cognome(w['text'].rstrip(','))
    ))

def _get_materia(words, gx_s, gx_e, y_start, y_end):
    """Estrae il testo della materia dalla zona sopra il marcatore orario."""
    ww = [w for w in words
          if gx_s <= w['x0'] <= gx_e
          and y_start <= w['top'] <= y_end
          and w['text'] not in SKIP_GLOBAL
          and w['text'] not in ORA_LABELS
          and w['text'] != '---'
          and not is_aula(w['text'])
          and not is_cognome(w['text'].rstrip(','))]
    return ' '.join(
        w['text'] for w in sorted(ww, key=lambda w: (w['top'], w['x0']))
    ).strip()[:70]

def parse_classe_page(page):
    """
    Estrae tutti gli slot orari da una pagina-classe.

    Struttura di ogni cella (dall'alto al basso):
      ┌─────────────────────────────┐
      │ [materia]   ← zona A        │  y: fine_slot_prec → marcatore_ora
      │  08:00  ←── marcatore ora   │
      │ [docente]   ← zona B        │  y: marcatore_ora → fine_slot
      │ [aula]                      │
      └─────────────────────────────┘

    Fix slot consecutivi: quando un docente occupa N ore di seguito,
    il suo nome appare UNA SOLA VOLTA nel PDF (visivamente un blocco unico).
    Se la zona B dello slot corrente è vuota, si cerca nella zona B
    dello slot precedente (stesso giorno/colonna).

    Ritorna: (nome_classe, [{'classe','giorno','ora','docenti','materia'}])
    """
    words = page.extract_words()
    if not words: return None, []

    # Nome classe: es "1A" a y ≈ 40-65
    classe_nome = None
    for w in words:
        if 40 <= w['top'] <= 65 and re.match(r'^\d[A-Z]{1,2}$', w['text']):
            classe_nome = w['text']
            break
    if not classe_nome: return None, []
    if not any(w['text'] in GIORNI_KEYS for w in words): return classe_nome, []

    # Posizioni x centrate per ogni colonna-giorno
    col_x = {}
    for w in words:
        if w['text'] in GIORNI_KEYS:
            col_x[GIORNO_NUM[w['text']]] = (w['x0'] + w['x1']) / 2
    if not col_x: return classe_nome, []

    sorted_cols = sorted(col_x.items(), key=lambda x: x[1])
    col_bounds = {}
    for i, (gnum, cx) in enumerate(sorted_cols):
        col_bounds[gnum] = (
            cx - 42,
            sorted_cols[i+1][1] - 42 if i+1 < len(sorted_cols) else cx + 95
        )

    # Posizioni y dei marcatori orario ("08:00" ecc.)
    ora_y = {}
    for w in words:
        if w['text'] in ORA_LABELS:
            ora_y[ORA_LABELS[w['text']]] = w['top']
    if not ora_y: return classe_nome, []

    sorted_oras = sorted(ora_y.items())  # [(1, y1), (2, y2), ...]
    header_y = next((w['top'] for w in words if w['text'] in GIORNI_KEYS), 70)

    slots = []
    for gnum, (gx_s, gx_e) in col_bounds.items():
        for i, (ora_num, y_marker) in enumerate(sorted_oras):

            # ── Zona A: materia (SOPRA il marcatore ora) ──
            mat_y_start = header_y + 3 if i == 0 else sorted_oras[i-1][1] + 37
            mat_y_end   = y_marker - 1

            # ── Zona B: docenti + aula (SOTTO il marcatore ora) ──
            doc_y_start = y_marker
            doc_y_end   = sorted_oras[i+1][1] - 3 if i+1 < len(sorted_oras) else y_marker + 75

            # Cerca docenti nella zona B corrente
            docenti = _get_docenti(words, gx_s, gx_e, doc_y_start, doc_y_end)

            # ── Fix slot consecutivi ──
            # Se zona B è vuota, il docente potrebbe essere nel blocco dello slot
            # precedente (stessa colonna), dove il suo nome appare visivamente
            # una sola volta per coprire N ore di fila.
            # Cerchiamo nella zona B dello slot precedente (doc_y dello prec).
            if not docenti and i > 0:
                prev_y_marker = sorted_oras[i-1][1]
                prev_doc_end  = y_marker - 3   # just before this slot's marker
                docenti = _get_docenti(words, gx_s, gx_e, prev_y_marker, prev_doc_end)

                # Se anche lo slot i-2 potrebbe contribuire (3 ore consecutive):
                if not docenti and i > 1:
                    prev2_y_marker = sorted_oras[i-2][1]
                    docenti = _get_docenti(words, gx_s, gx_e, prev2_y_marker, prev_doc_end)

            if not docenti:
                continue

            # Materia: zona A con esclusione di cognomi (che "traboccano" dal precedente)
            mat_words = [w for w in words
                         if gx_s <= w['x0'] <= gx_e
                         and mat_y_start <= w['top'] <= mat_y_end
                         and w['text'] not in SKIP_GLOBAL
                         and w['text'] not in ORA_LABELS
                         and w['text'] != '---'
                         and not is_aula(w['text'])
                         and not is_cognome(w['text'].rstrip(','))]
            materia = ' '.join(
                w['text'] for w in sorted(mat_words, key=lambda w: (w['top'], w['x0']))
            ).strip()[:70]

            slots.append({
                'classe':  classe_nome,
                'giorno':  gnum,
                'ora':     ora_num,
                'docenti': docenti,
                'materia': materia,
            })

    return classe_nome, slots


def parse_pdf_classi(pdf_path):
    all_slots = []
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        for idx, page in enumerate(pdf.pages):
            if idx % 15 == 0:
                print(f"   pagina {idx}/{n}…", end='\r', flush=True)
            _, slots = parse_classe_page(page)
            all_slots.extend(slots)
    print()
    return all_slots

# ─────────────────────────── IMPORTA IN DB ───────────────────────────

def importa(db_path, slots):
    # Assicura colonna materia
    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute('PRAGMA table_info(orario_docenti)').fetchall()]
    if 'materia' not in cols:
        conn.execute("ALTER TABLE orario_docenti ADD COLUMN materia TEXT DEFAULT ''")
        conn.commit()

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()

    ins_doc = ins_slot = ins_comp = 0
    _doc_cache   = {}
    _class_cache = {}

    def get_or_create_docente(cognome):
        if cognome in _doc_cache: return _doc_cache[cognome]
        row = conn.execute("SELECT id FROM docenti WHERE UPPER(cognome)=?", (cognome.upper(),)).fetchone()
        if not row:
            row = conn.execute("SELECT id FROM docenti WHERE UPPER(cognome) LIKE ?", (cognome.upper()+'%',)).fetchone()
        if row:
            _doc_cache[cognome] = row[0]; return row[0]
        cur.execute(
            "INSERT INTO docenti (cognome, nome, ruolo, plesso_id, ore_cattedra) VALUES (?,?,'curriculare',1,18)",
            (cognome.upper(), '')
        )
        nonlocal ins_doc; ins_doc += 1
        did = cur.lastrowid; _doc_cache[cognome] = did; return did

    def get_or_create_classe(nome):
        if nome in _class_cache: return _class_cache[nome]
        row = conn.execute("SELECT id FROM classi WHERE nome=?", (nome,)).fetchone()
        if row: _class_cache[nome] = row[0]; return row[0]
        m = re.match(r'(\d)([A-Z]+)', nome)
        anno, sez = (int(m.group(1)), m.group(2)) if m else (0, nome)
        cur.execute("INSERT INTO classi (nome, anno, sezione, plesso_id) VALUES (?,?,?,1)", (nome, anno, sez))
        cid = cur.lastrowid; _class_cache[nome] = cid; return cid

    conn.execute("DELETE FROM orario_docenti WHERE tipo='lezione-pdf'")
    conn.execute("DELETE FROM compresenze WHERE note='da-classi-pdf'")

    for slot in slots:
        cid  = get_or_create_classe(slot['classe'])
        dids = [get_or_create_docente(cog) for cog in slot['docenti']]
        mat  = slot.get('materia', '')

        for did in dids:
            ex = conn.execute(
                "SELECT 1 FROM orario_docenti WHERE docente_id=? AND classe_id=? AND giorno=? AND ora=?",
                (did, cid, slot['giorno'], slot['ora'])
            ).fetchone()
            if not ex:
                cur.execute(
                    "INSERT INTO orario_docenti (docente_id, classe_id, giorno, ora, tipo, materia) VALUES (?,?,?,?,'lezione-pdf',?)",
                    (did, cid, slot['giorno'], slot['ora'], mat)
                )
                ins_slot += 1

        if len(dids) >= 2:
            d1, d2 = min(dids[0], dids[1]), max(dids[0], dids[1])
            ex = conn.execute(
                "SELECT 1 FROM compresenze WHERE classe_id=? AND giorno=? AND ora=? AND docente1_id=? AND docente2_id=?",
                (cid, slot['giorno'], slot['ora'], d1, d2)
            ).fetchone()
            if not ex:
                cur.execute(
                    "INSERT INTO compresenze (classe_id, giorno, ora, docente1_id, docente2_id, note) VALUES (?,?,?,?,?,'da-classi-pdf')",
                    (cid, slot['giorno'], slot['ora'], d1, d2)
                )
                ins_comp += 1

    conn.commit(); conn.close()
    return {'docenti_creati': ins_doc, 'slot_orario': ins_slot, 'compresenze': ins_comp}

# ─────────────────────────── PARSER PDF DOCENTI (secondo passaggio) ──────────────────

_NON_COGNOMI_DOC = {
    'SISTEMI','RETI','INFORMATICA','MATEMATICA','ITALIANO','STORIA','INGLESE',
    'FISICA','CHIMICA','TECNOLOGIA','TECNOLOGIE','GRAFICA','MOTORIE','DIRITTO',
    'ECONOMIA','MECCANICA','MECCANICHE','AUTOMAZIONE','LABORATORI','TECNICI',
    'TEORIA','TELECOMUNICAZIONI','RELIGIONE','ELETTROT.','ELETTRON.',
    'BIOLO','TERRA','GEOGRAFIA','COMPL.','PROG.','MULTIMED.','ORG.','GEST.',
    'TEC.','PROC.','PROD.','INT.','SC.','(I)','(EL)','(ET)','(T)','E',
    'DI','DEL','F.','C.','D.','G.','M.','L.','V.','A.',
    'FE.','FR.','A.NIO','G.CO','G.PPE','M.C.','F.S.','ITTS','"E.','SCALFARO"',
}
_SKIP_DOC = {'ITTS','"E.','SCALFARO"','SCALFARO','Torna','alto','---','in'} | set(GIORNI_KEYS)

def _is_classe(s):
    return bool(re.match(r'^\d[A-Z]{1,2}$', s.strip()))

def parse_docente_pagina(page):
    """
    Estrae dal PDF orario-per-docente (orario_DOCENTI.pdf) l'elenco di slot.
    Ritorna (nome_doc, [{'giorno','ora','classe'}])
    """
    words = page.extract_words()
    if not words: return None, []

    SKIP_NOME = {'ITTS', '"E.', 'SCALFARO"', 'SCALFARO', 'E.'}
    nome_words = [w for w in words if 40 <= w['top'] <= 62 and w['text'] not in SKIP_NOME]
    if not nome_words: return None, []
    nome_doc = ' '.join(w['text'] for w in sorted(nome_words, key=lambda w: w['x0']))

    if not any(w['text'] in GIORNI_KEYS for w in words): return nome_doc, []

    col_x = {}
    for w in words:
        if w['text'] in GIORNI_KEYS:
            col_x[GIORNO_NUM[w['text']]] = (w['x0'] + w['x1']) / 2
    if not col_x: return nome_doc, []

    sorted_cols = sorted(col_x.items(), key=lambda x: x[1])
    col_bounds = {}
    for i, (gnum, cx) in enumerate(sorted_cols):
        col_bounds[gnum] = (cx - 35, sorted_cols[i+1][1] - 35 if i+1 < len(sorted_cols) else cx + 80)

    ora_y = {}
    for w in words:
        if w['text'] in ORA_LABELS:
            ora_y[ORA_LABELS[w['text']]] = w['top']
    if not ora_y: return nome_doc, []

    sorted_oras = sorted(ora_y.items())
    header_y = next((w['top'] for w in words if w['text'] in GIORNI_KEYS), 70)

    slots = []
    for gnum, (gx_s, gx_e) in col_bounds.items():
        prev_classe = None

        for i, (ora_num, y_marker) in enumerate(sorted_oras):
            mat_y_s = header_y + 3 if i == 0 else sorted_oras[i-1][1] + 37
            doc_y_e = sorted_oras[i+1][1] - 3 if i+1 < len(sorted_oras) else y_marker + 75

            cell_words = [w for w in words
                          if gx_s <= w['x0'] <= gx_e
                          and mat_y_s <= w['top'] <= doc_y_e
                          and w['text'] not in _SKIP_DOC
                          and w['text'] not in ORA_LABELS
                          and w['text'] != '---']

            classi = [w['text'] for w in cell_words if _is_classe(w['text'])]

            if not classi:
                # Slot consecutivo: propaga la classe precedente
                if prev_classe:
                    slots.append({'giorno': gnum, 'ora': ora_num, 'classe': prev_classe})
                else:
                    prev_classe = None
                continue

            classe = classi[0]
            prev_classe = classe
            slots.append({'giorno': gnum, 'ora': ora_num, 'classe': classe})

    return nome_doc, slots


def parse_pdf_docenti(pdf_path):
    """Legge il PDF orario_DOCENTI e ritorna dict cognome→[slots]."""
    risultato = {}
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        for idx, page in enumerate(pdf.pages):
            if idx % 20 == 0:
                print(f"   docenti pagina {idx}/{n}…", end='\r', flush=True)
            nome, slots = parse_docente_pagina(page)
            if nome and slots:
                # Normalizza cognome (prende solo la prima parola maiuscola)
                cognome = nome.split()[0].upper().rstrip('.')
                if cognome not in risultato:
                    risultato[cognome] = []
                risultato[cognome].extend(slots)
    print()
    return risultato


def ricalcola_compresenze(db_path):
    """
    Dopo aver importato tutti gli slot, trova automaticamente le compresenze:
    per ogni (classe_id, giorno, ora) con più di un docente, crea la compresenza.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    # Cancella le compresenze generate automaticamente da PDF (non manuali)
    conn.execute("DELETE FROM compresenze WHERE note IN ('da-classi-pdf','da-docenti-pdf')")

    ins = 0
    rows = conn.execute("""
        SELECT classe_id, giorno, ora, GROUP_CONCAT(docente_id ORDER BY docente_id) AS docenti
        FROM orario_docenti
        WHERE classe_id IS NOT NULL
        GROUP BY classe_id, giorno, ora
        HAVING COUNT(DISTINCT docente_id) >= 2
    """).fetchall()

    for row in rows:
        dids = [int(x) for x in row['docenti'].split(',')]
        cid  = row['classe_id']
        g    = row['giorno']
        o    = row['ora']
        # Crea compresenze per ogni coppia
        for i in range(len(dids)):
            for j in range(i+1, len(dids)):
                d1, d2 = dids[i], dids[j]
                ex = conn.execute(
                    "SELECT 1 FROM compresenze WHERE classe_id=? AND giorno=? AND ora=? "
                    "AND docente1_id=? AND docente2_id=?",
                    (cid, g, o, d1, d2)
                ).fetchone()
                if not ex:
                    cur.execute(
                        "INSERT INTO compresenze (classe_id, giorno, ora, docente1_id, docente2_id, note) "
                        "VALUES (?,?,?,?,?,'da-docenti-pdf')",
                        (cid, g, o, d1, d2)
                    )
                    ins += 1

    conn.commit()
    conn.close()
    return ins


def importa_docenti(db_path, slots_docenti):
    """
    Aggiunge gli slot del PDF docenti che mancano nel DB (dal PDF classi).
    Non sovrascrive slot già esistenti.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()

    ins_slot = 0
    _doc_cache   = {}
    _class_cache = {}

    def find_docente(cognome):
        if cognome in _doc_cache: return _doc_cache[cognome]
        row = conn.execute("SELECT id FROM docenti WHERE UPPER(cognome)=?", (cognome.upper(),)).fetchone()
        if not row:
            row = conn.execute("SELECT id FROM docenti WHERE UPPER(cognome) LIKE ?", (cognome.upper()+'%',)).fetchone()
        if row:
            _doc_cache[cognome] = row[0]; return row[0]
        return None  # non creo docenti nuovi in questo passaggio

    def find_classe(nome):
        if nome in _class_cache: return _class_cache[nome]
        row = conn.execute("SELECT id FROM classi WHERE nome=?", (nome,)).fetchone()
        if row:
            _class_cache[nome] = row[0]; return row[0]
        return None  # non creo classi nuove

    for cognome, slots in slots_docenti.items():
        did = find_docente(cognome)
        if not did: continue  # docente non nel DB → skip

        for slot in slots:
            cid = find_classe(slot['classe'])
            if not cid: continue

            ex = conn.execute(
                "SELECT 1 FROM orario_docenti WHERE docente_id=? AND giorno=? AND ora=?",
                (did, slot['giorno'], slot['ora'])
            ).fetchone()
            if not ex:
                cur.execute(
                    "INSERT INTO orario_docenti (docente_id, classe_id, giorno, ora, tipo, materia) "
                    "VALUES (?,?,?,?,'lezione-pdf','')",
                    (did, cid, slot['giorno'], slot['ora'])
                )
                ins_slot += 1

    conn.commit()
    conn.close()
    return ins_slot

# ─────────────────────────── MAIN ───────────────────────────

def main():
    ap = argparse.ArgumentParser(description='Supplentia – Importa Orario da PDF')
    ap.add_argument('--classi',  required=True,  help='PDF orario per classe (timbro_CLASSI_*.pdf)')
    ap.add_argument('--docenti', required=False, help='PDF orario per docente (orario_DOCENTI.pdf)')
    ap.add_argument('--db', default=DB_PATH)
    args = ap.parse_args()

    print(f"\n📄 Supplentia – Importazione Orario")
    print(f"{'─'*54}")

    # Passaggio 1: PDF classi
    print(f"📖 [1/3] PDF classi: {os.path.basename(args.classi)}")
    slots = parse_pdf_classi(args.classi)
    classi_n  = len(set(s['classe']  for s in slots))
    docenti_n = len(set(d for s in slots for d in s['docenti']))
    mat_n     = sum(1 for s in slots if s['materia'])
    print(f"   ✓ {len(slots)} slot · {classi_n} classi · {docenti_n} docenti · {mat_n} materie")

    print(f"\n💾 Importazione in: {args.db}")
    stats = importa(args.db, slots)
    print(f"   Docenti creati: {stats['docenti_creati']} · Slot: {stats['slot_orario']}")

    # Passaggio 2: PDF docenti (slot aggiuntivi)
    if args.docenti:
        print(f"\n📖 [2/3] PDF docenti: {os.path.basename(args.docenti)}")
        slots_doc = parse_pdf_docenti(args.docenti)
        n_doc  = len(slots_doc)
        n_slot = sum(len(v) for v in slots_doc.values())
        print(f"   ✓ {n_doc} docenti · {n_slot} slot letti")
        ins_extra = importa_docenti(args.db, slots_doc)
        print(f"   Slot aggiuntivi inseriti: {ins_extra}")
    else:
        print(f"\n   (Usa --docenti orario_DOCENTI.pdf per slot e compresenze complete)")

    # Passaggio 3: ricalcolo compresenze
    print(f"\n🔄 [3/3] Ricalcolo compresenze…")
    n_comp = ricalcola_compresenze(args.db)
    print(f"   ✓ {n_comp} nuove compresenze rilevate")

    print(f"\n{'─'*54}")
    print(f"✅ Importazione completata.")
    print()

if __name__ == '__main__':
    main()

