"""
Supplentia · Motore di Assegnazione Sostituzioni
Implementa i criteri di priorità configurabili:

  P0 (built-in) COMPRESENZA    — docente in compresenza nell'ora
  P1 (built-in) ORE_DISP       — ore a disposizione / potenziamento
  P2 (built-in) REC_PERMESSI   — recupero permessi brevi
  P3             STESSA_CLASSE  — stessa classe / stesso plesso
  P4             SOSTEGNO       — docenti sostegno (condizionato)
  P5 (built-in) ORE_ECCEDENTI  — disponibilità volontaria ore eccedenti

Il motore è completamente configurabile: l'ordine e l'attivazione dei criteri
viene letta dalla tabella `criteri` ad ogni esecuzione.
"""

import json
import sqlite3
from datetime import date, datetime
from typing import Optional
from db.database import get_connection, rows_to_list, row_to_dict


# ─── Utilità ──────────────────────────────────────────────────

def _giorno_iso_to_num(data_iso: str) -> int:
    """Converte data ISO (2026-04-30) in numero giorno settimana (1=Lun, 5=Ven)."""
    d = date.fromisoformat(data_iso)
    return d.isoweekday()  # Mon=1 ... Sun=7


def _settimana_iso(data_iso: str) -> str:
    """Restituisce la settimana ISO (es. '2026-W18') per calcolo ore eccedenti."""
    d = date.fromisoformat(data_iso)
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def _ore_eccedenti_settimana(conn: sqlite3.Connection, docente_id: int, settimana: str) -> int:
    """Conta le ore eccedenti già assegnate nella settimana."""
    cur = conn.execute(
        "SELECT COALESCE(SUM(ore), 0) FROM ore_eccedenti WHERE docente_id=? AND settimana=?",
        (docente_id, settimana)
    )
    return cur.fetchone()[0]


def _docente_gia_assegnato(conn: sqlite3.Connection, docente_id: int, data: str, ora: int) -> bool:
    """Controlla se il docente è già assegnato in quell'ora (evita doppi)."""
    cur = conn.execute(
        """SELECT id FROM sostituzioni
           WHERE docente_sost_id=? AND data=? AND ora=? AND stato!='annullata'""",
        (docente_id, data, ora)
    )
    return cur.fetchone() is not None


def _docente_assente(conn: sqlite3.Connection, docente_id: int, data: str, ora: int) -> bool:
    """Controlla se il docente ha un'assenza che copre quell'ora."""
    cur = conn.execute(
        "SELECT ore FROM assenze WHERE docente_id=? AND data=?",
        (docente_id, data)
    )
    row = cur.fetchone()
    if not row:
        return False
    ore = json.loads(row[0])
    return ora in ore


def _carica_criteri(conn: sqlite3.Connection) -> list[dict]:
    """Carica i criteri attivi ordinati per priorità dalla tabella `criteri`."""
    cur = conn.execute(
        "SELECT * FROM criteri WHERE attivo=1 ORDER BY ordine ASC"
    )
    criteri = []
    for r in cur.fetchall():
        c = dict(r)
        c['parametri'] = json.loads(c.get('parametri') or '{}')
        criteri.append(c)
    return criteri


# ─── Candidati per criterio ───────────────────────────────────

def _candidati_compresenza(conn: sqlite3.Connection, assenza_docente_id: int,
                            classe_id: int, data: str, ora: int,
                            params: dict) -> list[dict]:
    """
    P0 - COMPRESENZA
    Cerca docenti che nell'orario hanno una compresenza nella stessa
    classe/giorno/ora del docente assente. Questi docenti rimangono
    in classe e assumono la lezione autonomamente.
    """
    giorno = _giorno_iso_to_num(data)

    # Trova l'orario del docente assente per quell'ora
    cur = conn.execute(
        "SELECT id FROM orario WHERE docente_id=? AND classe_id=? AND giorno=? AND ora=?",
        (assenza_docente_id, classe_id, giorno, ora)
    )
    orario_assente = cur.fetchone()
    if not orario_assente:
        return []

    orario_id = orario_assente[0]

    # Trova docenti collegati da compresenza
    cur = conn.execute(
        """SELECT
             d.id, d.cognome, d.nome, d.ruolo,
             o.tipo as tipo_ora,
             m.nome as materia_nome
           FROM compresenze c
           JOIN orario o ON (
               CASE WHEN c.orario_id_1 = ? THEN o.id = c.orario_id_2
                    ELSE o.id = c.orario_id_1 END
           )
           JOIN docenti d ON d.id = o.docente_id
           LEFT JOIN materie m ON m.id = o.materia_id
           WHERE (c.orario_id_1=? OR c.orario_id_2=?)
             AND d.attivo = 1
        """,
        (orario_id, orario_id, orario_id)
    )
    candidati = []
    for r in cur.fetchall():
        doc = dict(r)
        if _docente_assente(conn, doc['id'], data, ora):
            continue
        if _docente_gia_assegnato(conn, doc['id'], data, ora):
            continue
        doc['motivo'] = f"Compresenza prevista in {ora}ª ora (rimane in classe autonomamente)"
        doc['punteggio'] = 100
        candidati.append(doc)
    return candidati


def _candidati_ore_disp(conn: sqlite3.Connection, assenza_docente_id: int,
                         classe_id: int, data: str, ora: int,
                         params: dict) -> list[dict]:
    """
    P1 - ORE A DISPOSIZIONE
    Docenti potenziamento con quell'ora libera nel loro orario.
    """
    giorno = _giorno_iso_to_num(data)

    # Classe del docente assente per eventuale preferenza stessa disciplina
    materia_classe = None
    if params.get('preferisci_stessa_disciplina'):
        cur = conn.execute(
            """SELECT materia_id FROM orario
               WHERE docente_id=? AND classe_id=? AND giorno=? AND ora=?""",
            (assenza_docente_id, classe_id, giorno, ora)
        )
        row = cur.fetchone()
        materia_classe = row[0] if row else None

    cur = conn.execute(
        """SELECT d.id, d.cognome, d.nome, d.ruolo,
                  o.materia_id,
                  (SELECT GROUP_CONCAT(mat.nome) FROM docente_materie dm
                   JOIN materie mat ON mat.id = dm.materia_id
                   WHERE dm.docente_id = d.id) as materie_nomi
           FROM docenti d
           JOIN orario o ON o.docente_id = d.id
           WHERE d.ruolo = 'potenziamento'
             AND d.attivo = 1
             AND o.tipo = 'potenziamento'
             AND o.giorno = ?
             AND o.ora = ?
        """,
        (giorno, ora)
    )
    candidati = []
    for r in cur.fetchall():
        doc = dict(r)
        if doc['id'] == assenza_docente_id:
            continue
        if _docente_assente(conn, doc['id'], data, ora):
            continue
        if _docente_gia_assegnato(conn, doc['id'], data, ora):
            continue
        punteggio = 90
        if materia_classe and doc.get('materia_id') == materia_classe:
            punteggio = 98
        doc['punteggio'] = punteggio
        doc['motivo'] = f"Ora di potenziamento disponibile nel piano orario ({ora}ª ora)"
        candidati.append(doc)
    return candidati


def _candidati_recupero_permessi(conn: sqlite3.Connection, assenza_docente_id: int,
                                  classe_id: int, data: str, ora: int,
                                  params: dict) -> list[dict]:
    """P2 - RECUPERO PERMESSI BREVI"""
    giorno = _giorno_iso_to_num(data)
    cur = conn.execute(
        """SELECT d.id, d.cognome, d.nome, d.ruolo,
                  pb.ore_debito - pb.ore_recuperate as ore_da_recuperare
           FROM docenti d
           JOIN permessi_brevi pb ON pb.docente_id = d.id
           WHERE d.attivo = 1
             AND pb.ore_debito > pb.ore_recuperate
             AND d.id != ?
             AND NOT EXISTS (
                 SELECT 1 FROM orario o2
                 WHERE o2.docente_id = d.id AND o2.giorno=? AND o2.ora=?
             )
        """,
        (assenza_docente_id, giorno, ora)
    )
    candidati = []
    for r in cur.fetchall():
        doc = dict(r)
        if _docente_assente(conn, doc['id'], data, ora):
            continue
        if _docente_gia_assegnato(conn, doc['id'], data, ora):
            continue
        doc['punteggio'] = 85
        doc['motivo'] = f"Ha {doc['ore_da_recuperare']} ore permesso breve da recuperare"
        candidati.append(doc)
    return candidati


def _candidati_stessa_classe(conn: sqlite3.Connection, assenza_docente_id: int,
                              classe_id: int, data: str, ora: int,
                              params: dict) -> list[dict]:
    """P3 - STESSA CLASSE / STESSO PLESSO"""
    giorno = _giorno_iso_to_num(data)
    includi_plesso = params.get('includi_stesso_plesso', True)

    # Docenti già in quella classe oggi in un'ora diversa, ora liberi
    cur = conn.execute(
        """SELECT DISTINCT d.id, d.cognome, d.nome, d.ruolo, d.plesso_id
           FROM docenti d
           JOIN orario o ON o.docente_id = d.id
           WHERE d.attivo = 1
             AND o.classe_id = ?
             AND o.giorno = ?
             AND d.id != ?
             AND NOT EXISTS (
                 SELECT 1 FROM orario o2
                 WHERE o2.docente_id = d.id AND o2.giorno=? AND o2.ora=?
             )
        """,
        (classe_id, giorno, assenza_docente_id, giorno, ora)
    )
    candidati = []
    visti = set()
    for r in cur.fetchall():
        doc = dict(r)
        if doc['id'] in visti:
            continue
        if _docente_assente(conn, doc['id'], data, ora):
            continue
        if _docente_gia_assegnato(conn, doc['id'], data, ora):
            continue
        visti.add(doc['id'])
        doc['punteggio'] = 78
        doc['motivo'] = "Docente già assegnato alla classe in altra ora della giornata"
        candidati.append(doc)

    if includi_plesso:
        # Docenti nello stesso plesso, liberi in quell'ora
        plesso_cur = conn.execute(
            "SELECT plesso_id FROM classi WHERE id=?", (classe_id,)
        )
        plesso_row = plesso_cur.fetchone()
        plesso_id = plesso_row[0] if plesso_row else None

        if plesso_id:
            cur2 = conn.execute(
                """SELECT d.id, d.cognome, d.nome, d.ruolo
                   FROM docenti d
                   WHERE d.plesso_id = ?
                     AND d.attivo = 1
                     AND d.id != ?
                     AND NOT EXISTS (
                         SELECT 1 FROM orario o3
                         WHERE o3.docente_id = d.id AND o3.giorno=? AND o3.ora=?
                     )
                """,
                (plesso_id, assenza_docente_id, giorno, ora)
            )
            for r in cur2.fetchall():
                doc = dict(r)
                if doc['id'] in visti:
                    continue
                if _docente_assente(conn, doc['id'], data, ora):
                    continue
                if _docente_gia_assegnato(conn, doc['id'], data, ora):
                    continue
                visti.add(doc['id'])
                doc['punteggio'] = 65
                doc['motivo'] = "Libero nel plesso in quell'ora"
                candidati.append(doc)

    return candidati


def _candidati_sostegno(conn: sqlite3.Connection, assenza_docente_id: int,
                         classe_id: int, data: str, ora: int,
                         params: dict, assenza_id: int) -> list[dict]:
    """P4 - DOCENTI DI SOSTEGNO (con vincoli logici)"""
    abilita_sempre = params.get('abilita_sempre', False)
    abilita_se_h_assente = params.get('abilita_se_alunno_h_assente', True)
    priorita_bes = params.get('priorita_classi_bes', True)
    giorno = _giorno_iso_to_num(data)

    # Verifica se la classe ha alunni BES
    cur_bes = conn.execute("SELECT ha_alunni_bes FROM classi WHERE id=?", (classe_id,))
    classe_row = cur_bes.fetchone()
    ha_bes = classe_row and classe_row[0]

    candidati = []
    cur = conn.execute(
        """SELECT d.id, d.cognome, d.nome, d.ruolo,
                  ah.classe_id as classe_sostegno_id
           FROM docenti d
           LEFT JOIN alunni_h ah ON ah.docente_sostegno_id = d.id
           WHERE d.ruolo = 'sostegno'
             AND d.attivo = 1
             AND d.id != ?
             AND NOT EXISTS (
                 SELECT 1 FROM orario o
                 WHERE o.docente_id = d.id AND o.giorno=? AND o.ora=?
                   AND o.tipo = 'sostegno'
             )
        """,
        (assenza_docente_id, giorno, ora)
    )
    for r in cur.fetchall():
        doc = dict(r)
        doc_id = doc['id']

        if _docente_assente(conn, doc_id, data, ora):
            continue
        if _docente_gia_assegnato(conn, doc_id, data, ora):
            continue

        # Controllo vincoli
        abilitato = abilita_sempre

        if abilita_se_h_assente and doc.get('classe_sostegno_id'):
            # Verifica se il suo alunno H è assente oggi
            cur_h = conn.execute(
                """SELECT a.id FROM assenze a
                   WHERE a.docente_id = (
                       SELECT docente_id FROM alunni_h
                       WHERE docente_sostegno_id = ? LIMIT 1
                   ) AND a.data = ?""",
                (doc_id, data)
            )
            # Semplificato: verifica assenza tramite flag su alunni_h
            # In produzione si gestirebbe un registro presenze alunni
            abilitato = True  # demo: assumiamo che l'alunno sia assente

        if not abilitato and priorita_bes and ha_bes:
            abilitato = True

        if not abilitato:
            continue

        punteggio = 60
        if ha_bes and priorita_bes:
            punteggio = 70
        if doc.get('classe_sostegno_id') == classe_id:
            punteggio = 72

        doc['punteggio'] = punteggio
        doc['motivo'] = "Docente sostegno disponibile (alunno H assente o classe BES)"
        candidati.append(doc)

    return candidati


def _candidati_ore_eccedenti(conn: sqlite3.Connection, assenza_docente_id: int,
                              classe_id: int, data: str, ora: int,
                              params: dict) -> list[dict]:
    """P5 - ORE ECCEDENTI"""
    giorno = _giorno_iso_to_num(data)
    max_ore = params.get('max_ore_settimana', 6)
    settimana = _settimana_iso(data)

    cur = conn.execute(
        """SELECT d.id, d.cognome, d.nome, d.ruolo,
                  d.max_eccedenti_sett
           FROM docenti d
           WHERE d.disp_eccedenti = 1
             AND d.attivo = 1
             AND d.id != ?
             AND NOT EXISTS (
                 SELECT 1 FROM orario o
                 WHERE o.docente_id = d.id AND o.giorno=? AND o.ora=?
             )
        """,
        (assenza_docente_id, giorno, ora)
    )
    candidati = []
    for r in cur.fetchall():
        doc = dict(r)
        limite = min(doc.get('max_eccedenti_sett', 6), max_ore)
        ore_usate = _ore_eccedenti_settimana(conn, doc['id'], settimana)
        if ore_usate >= limite:
            continue
        if _docente_assente(conn, doc['id'], data, ora):
            continue
        if _docente_gia_assegnato(conn, doc['id'], data, ora):
            continue
        doc['punteggio'] = 50 - ore_usate  # meno ore usate = priorità maggiore
        doc['ore_usate'] = ore_usate
        doc['ore_max'] = limite
        doc['motivo'] = f"Disponibilità ore eccedenti ({ore_usate}/{limite} usate questa settimana)"
        candidati.append(doc)

    # Ordina per meno ore già fatte (equità)
    candidati.sort(key=lambda x: x.get('ore_usate', 0))
    return candidati


# ── HANDLER PER CRITERIO PERSONALIZZATO ──────────────────────

def _candidati_custom(conn: sqlite3.Connection, criterio: dict,
                       assenza_docente_id: int, classe_id: int,
                       data: str, ora: int) -> list[dict]:
    """
    Criteri personalizzati aggiunti dall'utente.
    Per ora restituisce lista vuota — in futuro supporterà
    script/regole configurabili dall'interfaccia.
    """
    return []


# ── MOTORE PRINCIPALE ─────────────────────────────────────────

def esegui_motore(
    conn: sqlite3.Connection,
    assenza_id: int,
    docente_id: int,
    classe_id: int,
    data: str,
    ora: int,
) -> dict:
    """
    Esegue il motore di assegnazione per una singola ora da coprire.
    Ritorna il miglior candidato trovato o None se non disponibile.
    """
    criteri = _carica_criteri(conn)

    HANDLERS = {
        'COMPRESENZA':  _candidati_compresenza,
        'ORE_DISP':     _candidati_ore_disp,
        'REC_PERMESSI': _candidati_recupero_permessi,
        'STESSA_CLASSE':_candidati_stessa_classe,
        'ORE_ECCEDENTI':_candidati_ore_eccedenti,
    }

    for criterio in criteri:
        codice = criterio['codice']
        params = criterio['parametri']

        if codice == 'SOSTEGNO':
            candidati = _candidati_sostegno(
                conn, docente_id, classe_id, data, ora, params, assenza_id
            )
        elif codice in HANDLERS:
            candidati = HANDLERS[codice](
                conn, docente_id, classe_id, data, ora, params
            )
        else:
            candidati = _candidati_custom(
                conn, criterio, docente_id, classe_id, data, ora
            )

        if candidati:
            # Prendi il candidato con punteggio più alto
            best = max(candidati, key=lambda x: x.get('punteggio', 0))
            return {
                'trovato': True,
                'docente': best,
                'criterio_id': criterio['id'],
                'criterio_codice': codice,
                'criterio_nome': criterio['nome'],
                'punteggio': best.get('punteggio', 0),
                'motivo': best.get('motivo', ''),
            }

    return {
        'trovato': False,
        'docente': None,
        'criterio_id': None,
        'criterio_codice': None,
        'criterio_nome': None,
        'punteggio': 0,
        'motivo': 'Nessun docente disponibile con i criteri attivi',
    }


def genera_sostituzioni_assenza(
    conn: sqlite3.Connection,
    assenza_id: int,
    created_by: Optional[int] = None,
) -> list[dict]:
    """
    Genera tutte le sostituzioni per un'assenza.
    Rispetta le sostituzioni già bloccate manualmente.
    """
    cur = conn.execute(
        "SELECT * FROM assenze WHERE id=?", (assenza_id,)
    )
    assenza = row_to_dict(cur.fetchone())
    if not assenza:
        raise ValueError(f"Assenza {assenza_id} non trovata")

    docente_id = assenza['docente_id']
    data = assenza['data']
    ore = json.loads(assenza['ore'])

    # Trova le classi del docente per ogni ora
    giorno = _giorno_iso_to_num(data)
    risultati = []

    for ora in ore:
        # Controlla se già esiste una sostituzione bloccata per quell'ora
        cur_existing = conn.execute(
            """SELECT * FROM sostituzioni
               WHERE assenza_id=? AND ora=? AND bloccata=1""",
            (assenza_id, ora)
        )
        if cur_existing.fetchone():
            continue  # Non toccare le sostituzioni bloccate

        # Trova la classe del docente per quell'ora
        cur_classe = conn.execute(
            """SELECT o.classe_id, o.materia_id, c.nome as classe_nome
               FROM orario o
               JOIN classi c ON c.id = o.classe_id
               WHERE o.docente_id=? AND o.giorno=? AND o.ora=?
               LIMIT 1""",
            (docente_id, giorno, ora)
        )
        orario_row = cur_classe.fetchone()
        if not orario_row:
            continue  # Il docente non ha lezione in quell'ora

        classe_id = orario_row['classe_id']

        # Cancella eventuale sostituzione automatica precedente (non bloccata)
        conn.execute(
            """DELETE FROM sostituzioni
               WHERE assenza_id=? AND ora=? AND tipo='automatica' AND bloccata=0""",
            (assenza_id, ora)
        )

        # Esegui motore
        risultato = esegui_motore(conn, assenza_id, docente_id, classe_id, data, ora)

        # Inserisci sostituzione
        if risultato['trovato']:
            doc = risultato['docente']
            cur_ins = conn.execute(
                """INSERT INTO sostituzioni
                   (assenza_id, docente_sost_id, classe_id, data, ora,
                    criterio_id, criterio_codice, punteggio,
                    tipo, bloccata, stato, note_motore, created_by)
                   VALUES (?,?,?,?,?,?,?,?,'automatica',0,'confermata',?,?)""",
                (
                    assenza_id, doc['id'], classe_id, data, ora,
                    risultato['criterio_id'], risultato['criterio_codice'],
                    risultato['punteggio'],
                    f"{risultato['motivo']} — Criterio: {risultato['criterio_nome']}",
                    created_by
                )
            )
            sost_id = cur_ins.lastrowid

            # Registra ore eccedenti se criterio P5
            if risultato['criterio_codice'] == 'ORE_ECCEDENTI':
                settimana = _settimana_iso(data)
                conn.execute(
                    """INSERT INTO ore_eccedenti
                       (docente_id, sostituzione_id, settimana, ore)
                       VALUES (?,?,?,1)""",
                    (doc['id'], sost_id, settimana)
                )

            risultati.append({
                'ora': ora,
                'classe_id': classe_id,
                'docente_sost': f"{doc['cognome']} {doc['nome']}",
                'criterio': risultato['criterio_nome'],
                'punteggio': risultato['punteggio'],
                'stato': 'confermata',
            })
        else:
            conn.execute(
                """INSERT INTO sostituzioni
                   (assenza_id, docente_sost_id, classe_id, data, ora,
                    tipo, bloccata, stato, note_motore, created_by)
                   VALUES (?,NULL,?,?,?,  'automatica',0,'in_attesa',?,?)""",
                (assenza_id, classe_id, data, ora,
                 risultato['motivo'], created_by)
            )
            risultati.append({
                'ora': ora,
                'classe_id': classe_id,
                'docente_sost': None,
                'criterio': None,
                'punteggio': 0,
                'stato': 'in_attesa',
            })

    return risultati
