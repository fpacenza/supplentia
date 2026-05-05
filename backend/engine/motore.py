#!/usr/bin/env python3
"""
SubstManager v2 – Motore Decisionale

Criteri configurabili dall'interfaccia (possono essere abilitati/disabilitati e riordinati):
  compresenza    → P0: secondo docente della compresenza (fisso, non disabilitabile)
  ore_disp       → P1: docente con ora a disposizione registrata
  rec_permessi   → P2: docente con permesso da recuperare
  stessa_classe  → P3: docente della stessa classe con ora disp.
  anticipo       → P6: docente dell'ora successiva anticipa (classe esce prima)
  sostegno       → P4: docente sostegno libero
  ore_eccedenti  → P5: docente disponibile per ore eccedenti
  entrata_uscita → P7: entrata ritardata / uscita anticipata (fallback finale)

I criteri vengono eseguiti NELL'ORDINE definito dal config, saltando quelli disabilitati.
"""

import json
import sqlite3
from datetime import date


# ─────────────────────────── HELPER ───────────────────────────

def settimana(d: str) -> str:
    dt = date.fromisoformat(d)
    return f"{dt.year}-W{dt.isocalendar()[1]:02d}"

def giorno_settimana(d: str) -> int:
    return date.fromisoformat(d).isoweekday()

def ore_da_json(ore_json: str) -> list:
    try:
        return json.loads(ore_json)
    except Exception:
        return []

def docenti_assenti_nel_giorno(conn, data: str) -> set:
    rows = conn.execute(
        "SELECT DISTINCT docente_id FROM assenze WHERE data=?", (data,)
    ).fetchall()
    return {r[0] for r in rows}

def docenti_occupati(conn, data: str, ora: int, assenti: set = None) -> set:
    rows = conn.execute(
        """SELECT docente_sostituto_id FROM sostituzioni
           WHERE data=? AND ora=? AND stato NOT IN ('annullata','uscita_anticipata','entrata_ritardata')
             AND docente_sostituto_id IS NOT NULL""",
        (data, ora)
    ).fetchall()
    occupati = {r[0] for r in rows}
    if assenti:
        occupati |= assenti
    return occupati

def docente_ha_lezione(conn, docente_id: int, giorno: int, ora: int,
                       data: str = None) -> bool:
    """True se il docente ha una lezione propria in quell'ora.
    Se data è fornita, ignora le classi in uscita didattica."""
    row = conn.execute(
        "SELECT classe_id FROM orario_docenti WHERE docente_id=? AND giorno=? AND ora=?",
        (docente_id, giorno, ora)
    ).fetchone()
    if not row:
        return False
    if data and row[0]:
        # Controlla se quella classe è in uscita didattica
        try:
            uscita = conn.execute(
                "SELECT ore_json FROM uscite_didattiche WHERE data=? AND classe_id=?",
                (data, row[0])
            ).fetchone()
        except Exception:
            uscita = None
        if uscita:
            try:
                ore_uscita = json.loads(uscita[0]) if uscita[0] else list(range(1,7))
            except Exception:
                ore_uscita = list(range(1,7))
            if ora in ore_uscita:
                return False   # classe in uscita → docente fisicamente libero
    return True

def docente_libero_nell_ora(conn, docente_id: int, giorno: int, ora: int,
                            data: str = None) -> bool:
    return not docente_ha_lezione(conn, docente_id, giorno, ora, data)

def ore_classe_nel_giorno(conn, classe_id: int, giorno: int) -> list:
    rows = conn.execute(
        "SELECT DISTINCT ora FROM orario_docenti WHERE classe_id=? AND giorno=? ORDER BY ora",
        (classe_id, giorno)
    ).fetchall()
    return [r[0] for r in rows]


# ─────────────────────────── CRITERI ───────────────────────────

def criterio_compresenza(conn, classe_id, giorno, ora, doc_assente_id, occupati):
    """P0 – Sempre attivo: il partner di compresenza copre."""
    risultati = []
    rows = conn.execute(
        "SELECT docente1_id, docente2_id, note FROM compresenze WHERE classe_id=? AND giorno=? AND ora=?",
        (classe_id, giorno, ora)
    ).fetchall()
    for d1, d2, note in rows:
        partner = d2 if d1 == doc_assente_id else (d1 if d2 == doc_assente_id else None)
        if partner is None:
            for cand in sorted([d1, d2]):
                if cand != doc_assente_id and cand not in occupati:
                    risultati.append({'docente_id': cand, 'punteggio': 95,
                                      'motivazione': f'Compresenza in classe ({note or ""})'})
        else:
            if partner not in occupati:
                risultati.append({'docente_id': partner, 'punteggio': 100,
                                  'motivazione': f'Compresenza registrata ({note or ""})'})
    return risultati


def criterio_ore_disposizione(conn, plesso_id, giorno, ora, occupati, params):
    """P1 – Ora a disposizione / potenziamento registrata."""
    risultati = []
    rows = conn.execute(
        """SELECT d.id, d.cognome, d.nome, od.tipo
           FROM orario_docenti od JOIN docenti d ON d.id=od.docente_id
           WHERE od.giorno=? AND od.ora=? AND od.tipo IN ('disposizione','potenziamento')
             AND d.plesso_id=? AND d.escluso_motore=0
           ORDER BY d.cognome, d.nome""",
        (giorno, ora, plesso_id)
    ).fetchall()
    for did, cognome, nome, tipo in rows:
        if did in occupati: continue
        score = 90 if tipo == 'disposizione' else 80
        risultati.append({'docente_id': did, 'punteggio': score,
                          'motivazione': f'{cognome} {nome} – ora {tipo}'})
    return risultati


def criterio_recupero_permessi(conn, plesso_id, giorno, ora, occupati):
    """P2 – Docente con permesso da recuperare."""
    risultati = []
    rows = conn.execute(
        """SELECT d.id, d.cognome, d.nome, pr.ore_da_recuperare
           FROM permessi_recupero pr JOIN docenti d ON d.id=pr.docente_id
           WHERE pr.ore_da_recuperare > 0 AND d.plesso_id=? AND d.escluso_motore=0
           ORDER BY pr.ore_da_recuperare DESC, d.cognome""",
        (plesso_id,)
    ).fetchall()
    for did, cognome, nome, ore in rows:
        if did in occupati: continue
        if docente_libero_nell_ora(conn, did, giorno, ora):
            risultati.append({'docente_id': did, 'punteggio': 88 + min(ore, 5),
                              'motivazione': f'{cognome} {nome} – {ore}h permesso da recuperare'})
    return risultati


def criterio_stessa_classe(conn, classe_id, giorno, ora, occupati):
    """P3 – Docente già nella classe con ora a disposizione in quell'ora."""
    risultati = []
    doc_in_classe = conn.execute(
        """SELECT DISTINCT od.docente_id FROM orario_docenti od
           WHERE od.classe_id=? AND od.giorno=? AND od.docente_id NOT IN (
               SELECT id FROM docenti WHERE escluso_motore=1
           )""",
        (classe_id, giorno)
    ).fetchall()
    for (did,) in doc_in_classe:
        if did in occupati: continue
        ha_disp = conn.execute(
            "SELECT 1 FROM orario_docenti WHERE docente_id=? AND giorno=? AND ora=? AND tipo IN ('disposizione','potenziamento')",
            (did, giorno, ora)
        ).fetchone()
        if ha_disp:
            d = conn.execute("SELECT cognome, nome FROM docenti WHERE id=?", (did,)).fetchone()
            risultati.append({'docente_id': did, 'punteggio': 75,
                              'motivazione': f'{d["cognome"]} {d["nome"]} – già nella classe (ora disp.)'})
    risultati.sort(key=lambda x: x['docente_id'])
    return risultati


def criterio_anticipo(conn, classe_id, giorno, ora, doc_assente_id, occupati, ore_assenza_classe):
    """P6 – Il docente dell'ora successiva anticipa (classe esce prima)."""
    if not classe_id: return []
    risultati = []
    ore_succ = conn.execute(
        """SELECT DISTINCT od.ora, od.docente_id, d.cognome, d.nome
           FROM orario_docenti od JOIN docenti d ON d.id=od.docente_id
           WHERE od.classe_id=? AND od.giorno=? AND od.ora > ?
           ORDER BY od.ora, d.cognome""",
        (classe_id, giorno, ora)
    ).fetchall()
    per_ora = {}
    for r in ore_succ:
        per_ora.setdefault(r[0], []).append(r)
    for ora_succ in sorted(per_ora.keys()):
        if ora_succ > ora + 1: break
        for r in per_ora[ora_succ]:
            did = r[1]
            if did == doc_assente_id or did in occupati: continue
            if docente_libero_nell_ora(conn, did, giorno, ora):
                risultati.append({'docente_id': did, 'punteggio': 70, 'tipo_spec': 'anticipo',
                                  'motivazione': f'{r[2]} {r[3]} – anticipa l\'ora {ora_succ}ª alla {ora}ª (classe esce prima)'})
        if risultati: break
    return risultati


def criterio_sostegno(conn, classe_id, data, giorno, ora, occupati, params):
    """P4 – Docente sostegno libero."""
    risultati = []
    ha_alunno_h = conn.execute("SELECT 1 FROM alunni_h WHERE classe_id=?", (classe_id,)).fetchone()
    if not ha_alunno_h and not params.get('abilita_sempre'): return []
    rows = conn.execute(
        "SELECT d.id, d.cognome, d.nome FROM docenti d WHERE d.ruolo='sostegno' AND d.escluso_motore=0 ORDER BY d.cognome"
    ).fetchall()
    for did, cognome, nome in rows:
        if did in occupati: continue
        if docente_libero_nell_ora(conn, did, giorno, ora):
            risultati.append({'docente_id': did, 'punteggio': 65,
                              'motivazione': f'{cognome} {nome} – docente sostegno libero'})
    return risultati


def criterio_ore_eccedenti(conn, plesso_id, data, giorno, ora, occupati, params):
    """P5 – Docente con disponibilità esplicita ore eccedenti, equità per settimana e storico."""
    max_ore = params.get('max_ore_settimana', 6)
    sett = settimana(data)
    risultati = []
    rows = conn.execute(
        """SELECT d.id, d.cognome, d.nome FROM docenti d
           WHERE d.disp_ore_eccedenti=1 AND d.plesso_id=? AND d.escluso_motore=0
           ORDER BY d.cognome""",
        (plesso_id,)
    ).fetchall()
    for did, cognome, nome in rows:
        if did in occupati: continue
        n_sett = conn.execute(
            "SELECT COUNT(*) FROM ore_eccedenti WHERE docente_id=? AND settimana=?", (did, sett)
        ).fetchone()[0]
        if n_sett >= max_ore: continue
        if not docente_libero_nell_ora(conn, did, giorno, ora): continue
        n_tot = conn.execute("SELECT COUNT(*) FROM ore_eccedenti WHERE docente_id=?", (did,)).fetchone()[0]
        punteggio = round(max(50 - n_sett * 5, 10) - n_tot * 0.01, 3)
        risultati.append({'docente_id': did, 'punteggio': punteggio,
                          'motivazione': f'{cognome} {nome} – {n_sett}/{max_ore} ore eccedenti sett.'
                                         + (f' ({n_tot} totali)' if n_tot > 0 else '')})
    return risultati


def criterio_entrata_uscita(conn, classe_id, giorno, ora, ore_assenza_classe):
    """P7 – Entrata ritardata / uscita anticipata (solo ore di testa/coda)."""
    if not classe_id: return []
    tutte_ore = ore_classe_nel_giorno(conn, classe_id, giorno)
    if not tutte_ore: return []
    risultati = []
    ore_dopo  = [o for o in tutte_ore if o > ora  and o not in ore_assenza_classe]
    ore_prima = [o for o in tutte_ore if o < ora  and o not in ore_assenza_classe]
    if not ore_dopo:
        risultati.append({'docente_id': None, 'punteggio': 20, 'tipo_spec': 'uscita_anticipata',
                          'motivazione': f'Uscita anticipata – nessuna lezione dopo l\'ora {ora}ª'})
    if not ore_prima:
        risultati.append({'docente_id': None, 'punteggio': 20, 'tipo_spec': 'entrata_ritardata',
                          'motivazione': f'Entrata ritardata – nessuna lezione prima dell\'ora {ora}ª'})
    return risultati




def docenti_liberi_per_uscita(conn, data: str, giorno: int, ora: int) -> set:
    """Docenti fisicamente liberi perché la loro classe è in uscita in quell'ora."""
    try:
        uscite = conn.execute(
            "SELECT classe_id, ore_json FROM uscite_didattiche WHERE data=?", (data,)
        ).fetchall()
    except Exception:
        return set()
    classi_uscita = set()
    for u_cid, u_ore_json in uscite:
        try:
            ore_uscita = json.loads(u_ore_json) if u_ore_json else list(range(1,7))
        except Exception:
            ore_uscita = list(range(1,7))
        if ora in ore_uscita:
            classi_uscita.add(u_cid)
    if not classi_uscita:
        return set()
    placeholders = ','.join('?' * len(classi_uscita))
    rows = conn.execute(
        f"SELECT DISTINCT docente_id FROM orario_docenti WHERE classe_id IN ({placeholders}) AND giorno=? AND ora=?",
        list(classi_uscita) + [giorno, ora]
    ).fetchall()
    return {r[0] for r in rows}


def criterio_uscita_didattica(conn, data, giorno, ora, classe_id, occupati):
    """
    Px – USCITA DIDATTICA: docente la cui classe è in uscita in quell'ora.
    Il docente è fisicamente libero ma disponibile SOLO per coprire
    quell'ora (non si può usare in ore diverse da quelle dell'uscita).
    Priorità 85: tra P1 (ore_disp=90) e P3 (stessa_classe=75).
    """
    risultati = []
    # Recupera tutte le uscite della data con il json delle ore
    try:
        uscite = conn.execute(
            "SELECT classe_id, ore_json FROM uscite_didattiche WHERE data=?", (data,)
        ).fetchall()
    except Exception:
        return []
    # Costruisce set di classe_id in uscita in quell'ora
    classi_uscita = set()
    for u_cid, u_ore_json in uscite:
        try:
            ore_uscita = json.loads(u_ore_json) if u_ore_json else list(range(1,7))
        except Exception:
            ore_uscita = list(range(1,7))
        if ora in ore_uscita:
            classi_uscita.add(u_cid)
    if not classi_uscita:
        return []
    # Trova i docenti che in quell'ora hanno lezione in una classe in uscita
    placeholders = ','.join('?' * len(classi_uscita))
    rows = conn.execute(
        f"""SELECT DISTINCT od.docente_id, d.cognome, d.nome
            FROM orario_docenti od JOIN docenti d ON d.id=od.docente_id
            WHERE od.classe_id IN ({placeholders})
              AND od.giorno=? AND od.ora=?
              AND d.escluso_motore=0
            ORDER BY d.cognome""",
        list(classi_uscita) + [giorno, ora]
    ).fetchall()
    for did, cognome, nome in rows:
        if did in occupati:
            continue
        risultati.append({
            'docente_id': did,
            'punteggio':  85,
            'motivazione': f'{cognome} {nome} – libero per uscita didattica della sua classe'
        })
    return risultati

# ─────────────── DISPATCH: mappa id criterio → funzione ───────────────

def _esegui_criterio(cid, params, conn, classe_id, giorno, ora,
                     doc_assente_id, occupati, ore_assenza_classe,
                     plesso_id, data):
    """Chiama la funzione giusta per l'id criterio dato."""
    if cid == 'compresenza' and classe_id:
        return criterio_compresenza(conn, classe_id, giorno, ora, doc_assente_id, occupati)
    if cid == 'uscita_didattica' and classe_id:
        return criterio_uscita_didattica(conn, data, giorno, ora, classe_id, occupati)
    if cid == 'ore_disp':
        return criterio_ore_disposizione(conn, plesso_id, giorno, ora, occupati, params)
    if cid == 'rec_permessi':
        return criterio_recupero_permessi(conn, plesso_id, giorno, ora, occupati)
    if cid == 'stessa_classe' and classe_id:
        return criterio_stessa_classe(conn, classe_id, giorno, ora, occupati)
    if cid == 'anticipo' and classe_id:
        return criterio_anticipo(conn, classe_id, giorno, ora, doc_assente_id, occupati, ore_assenza_classe)
    if cid == 'sostegno' and classe_id:
        return criterio_sostegno(conn, classe_id, data, giorno, ora, occupati, params)
    if cid == 'ore_eccedenti':
        return criterio_ore_eccedenti(conn, plesso_id, data, giorno, ora, occupati, params)
    if cid == 'entrata_uscita' and classe_id:
        return criterio_entrata_uscita(conn, classe_id, giorno, ora, ore_assenza_classe)
    # criteri custom: trattati come ore_disp
    if cid.startswith('custom_'):
        return criterio_ore_disposizione(conn, plesso_id, giorno, ora, occupati, params)
    return []


# ─────────────────────────── MOTORE PRINCIPALE ───────────────────────────

def run_engine(conn: sqlite3.Connection, data: str, config: dict, forza_ricalcolo: bool = False) -> dict:
    # Costruisce la lista criteri ATTIVI nell'ordine definito dal config
    # La compresenza (P0) è sempre presente e SEMPRE PRIMA, non disabilitabile
    compresenza_cfg = {'id': 'compresenza', 'attivo': True, 'priorita': 0, 'parametri': {}}

    criteri_attivi = [compresenza_cfg] + sorted(
        [c for c in config.get('criteri', []) + config.get('criteri_custom', [])
         if c.get('attivo', True) and c.get('id') != 'compresenza'],
        key=lambda c: c.get('priorita', 99)
    )

    giorno = giorno_settimana(data)
    if giorno > 6:
        return {'errore': 'Domenica: nessuna sostituzione', 'sostituzioni': []}

    plesso_default = 1

    assenze = conn.execute(
        """SELECT a.id, a.docente_id, a.ore_json, d.plesso_id
           FROM assenze a JOIN docenti d ON d.id=a.docente_id
           WHERE a.data=? ORDER BY a.id""",
        (data,)
    ).fetchall()

    ore_assenza_per_classe = {}
    for ass_id, doc_id, ore_json, plesso_id in assenze:
        for ora in sorted(ore_da_json(ore_json)):
            slot = conn.execute(
                "SELECT classe_id FROM orario_docenti WHERE docente_id=? AND giorno=? AND ora=?",
                (doc_id, giorno, ora)
            ).fetchone()
            if slot and slot[0]:
                ore_assenza_per_classe.setdefault(slot[0], set()).add(ora)

    assenti_oggi = docenti_assenti_nel_giorno(conn, data)

    generate = []
    coperte  = 0
    non_coperte = 0

    if forza_ricalcolo:
        conn.execute(
            "DELETE FROM ore_eccedenti WHERE sostituzione_id IN (SELECT id FROM sostituzioni WHERE data=? AND bloccata=0)",
            (data,)
        )
        conn.execute("DELETE FROM sostituzioni WHERE data=? AND bloccata=0", (data,))
        conn.commit()

    for ass_id, doc_assente_id, ore_json, plesso_id in assenze:
        ore = sorted(ore_da_json(ore_json))
        plesso_id = plesso_id or plesso_default

        for ora in ore:
            slot = conn.execute(
                "SELECT classe_id FROM orario_docenti WHERE docente_id=? AND giorno=? AND ora=?",
                (doc_assente_id, giorno, ora)
            ).fetchone()
            if not slot: continue
            classe_id = slot[0]
            if not classe_id: continue

            # Già bloccata manualmente?
            if conn.execute("SELECT 1 FROM sostituzioni WHERE assenza_id=? AND ora=? AND bloccata=1",
                            (ass_id, ora)).fetchone():
                continue

            # Già confermata (run normale)?
            if not forza_ricalcolo and conn.execute(
                "SELECT 1 FROM sostituzioni WHERE assenza_id=? AND ora=? AND bloccata=0 "
                "AND stato IN ('confermata','uscita_anticipata','entrata_ritardata','anticipo')",
                (ass_id, ora)
            ).fetchone():
                continue

            occupati = docenti_occupati(conn, data, ora, assenti_oggi)

            # Slot già coperto da un partner (compresenza con entrambi assenti)?
            già_coperto = conn.execute(
                """SELECT s.docente_sostituto_id FROM sostituzioni s
                   WHERE s.data=? AND s.classe_id=? AND s.ora=?
                     AND s.docente_assente_id != ?
                     AND s.stato IN ('confermata','anticipo','uscita_anticipata','entrata_ritardata')
                   LIMIT 1""",
                (data, classe_id, ora, doc_assente_id)
            ).fetchone()
            if già_coperto:
                conn.execute(
                    "DELETE FROM ore_eccedenti WHERE sostituzione_id IN "
                    "(SELECT id FROM sostituzioni WHERE assenza_id=? AND ora=? AND bloccata=0)",
                    (ass_id, ora)
                )
                conn.execute("DELETE FROM sostituzioni WHERE assenza_id=? AND ora=? AND bloccata=0", (ass_id, ora))
                conn.execute(
                    "INSERT INTO sostituzioni (assenza_id, data, docente_assente_id, docente_sostituto_id, "
                    "classe_id, ora, criterio_id, punteggio, tipo, stato, motivazione) "
                    "VALUES (?,?,?,?,?,?,'compresenza_assente',100,'auto','confermata','Coperto: stessa classe/ora già assegnata a sostituto comune')",
                    (ass_id, data, doc_assente_id, già_coperto[0], classe_id, ora)
                )
                conn.commit()
                coperte += 1
                generate.append({'ora': ora, 'classe_id': classe_id, 'doc_assente': doc_assente_id,
                                  'doc_sostituto': già_coperto[0], 'tipo': 'auto', 'stato': 'confermata', 'punteggio': 100})
                continue

            ore_assenza_classe = ore_assenza_per_classe.get(classe_id, set())

            # ── Applica i criteri ATTIVI nell'ordine configurato ──────────────
            candidati = []
            tipo_risoluzione = 'sostituzione'

            for criterio in criteri_attivi:
                cid    = criterio['id']
                params = criterio.get('parametri', {})

                c = _esegui_criterio(cid, params, conn, classe_id, giorno, ora,
                                     doc_assente_id, occupati, ore_assenza_classe,
                                     plesso_id, data)
                if c:
                    candidati = c
                    if cid == 'anticipo':
                        tipo_risoluzione = 'anticipo'
                    elif cid in ('entrata_uscita',):
                        tipo_risoluzione = c[0].get('tipo_spec', 'entrata_uscita')
                    break   # ← criteri a cascata: il primo che trova vince

            # ── Selezione migliore (deterministica) ───────────────────────────
            unici = {}
            for cand in candidati:
                key = cand['docente_id'] if cand['docente_id'] is not None else 'null'
                if key not in unici or cand['punteggio'] > unici[key]['punteggio']:
                    unici[key] = cand
            migliore = sorted(unici.values(),
                              key=lambda x: (-x['punteggio'], x['docente_id'] if x['docente_id'] else 9999)
                              )[0] if unici else None

            # ── Stato e tipo ──────────────────────────────────────────────────
            if migliore:
                ts = migliore.get('tipo_spec', '')
                if ts == 'uscita_anticipata':
                    stato_sost, tipo_sost, crit_id = 'uscita_anticipata', 'uscita_anticipata', 'entrata_uscita'
                elif ts == 'entrata_ritardata':
                    stato_sost, tipo_sost, crit_id = 'entrata_ritardata', 'entrata_ritardata', 'entrata_uscita'
                elif ts == 'anticipo':
                    stato_sost, tipo_sost, crit_id = 'confermata', 'anticipo', 'anticipo'
                else:
                    stato_sost, tipo_sost = 'confermata', 'auto'
                    p = migliore['punteggio']
                    if p >= 95:   crit_id = 'compresenza'
                    elif p >= 80: crit_id = 'ore_disp'
                    elif p >= 88: crit_id = 'rec_permessi'
                    elif p >= 75: crit_id = 'stessa_classe'
                    elif p >= 65: crit_id = 'sostegno'
                    else:         crit_id = 'ore_eccedenti'
                doc_sost_id = migliore['docente_id']
            else:
                stato_sost, tipo_sost, crit_id, doc_sost_id = 'attesa', 'auto', None, None

            # ── Scrivi in DB ──────────────────────────────────────────────────
            if not forza_ricalcolo:
                conn.execute(
                    "DELETE FROM ore_eccedenti WHERE sostituzione_id IN "
                    "(SELECT id FROM sostituzioni WHERE assenza_id=? AND ora=? AND bloccata=0 AND stato='attesa')",
                    (ass_id, ora)
                )
                conn.execute(
                    "DELETE FROM sostituzioni WHERE assenza_id=? AND ora=? AND bloccata=0 AND stato='attesa'",
                    (ass_id, ora)
                )

            r_sost = conn.execute(
                "INSERT INTO sostituzioni (assenza_id, data, docente_assente_id, docente_sostituto_id, "
                "classe_id, ora, criterio_id, punteggio, tipo, stato, motivazione) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (ass_id, data, doc_assente_id, doc_sost_id, classe_id, ora, crit_id,
                 migliore['punteggio'] if migliore else 0, tipo_sost, stato_sost,
                 migliore['motivazione'] if migliore else 'Nessun docente disponibile')
            )

            # Registra ora eccedente se P5
            if doc_sost_id and crit_id == 'ore_eccedenti' and stato_sost == 'confermata':
                conn.execute(
                    "INSERT INTO ore_eccedenti (docente_id, sostituzione_id, data, settimana) VALUES (?,?,?,?)",
                    (doc_sost_id, r_sost.lastrowid, data, settimana(data))
                )

            if migliore:
                coperte += 1
            else:
                non_coperte += 1

            generate.append({'ora': ora, 'classe_id': classe_id, 'doc_assente': doc_assente_id,
                              'doc_sostituto': doc_sost_id, 'tipo': tipo_sost, 'stato': stato_sost,
                              'punteggio': migliore['punteggio'] if migliore else 0})

    conn.commit()
    return {'data': data, 'assenze': len(assenze), 'slot_totali': len(generate),
            'coperte': coperte, 'non_coperte': non_coperte,
            'percentuale': round(coperte / len(generate) * 100) if generate else 0,
            'sostituzioni': generate}
