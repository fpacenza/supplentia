#!/usr/bin/env python3
"""
SubstManager v2 – Server HTTP
Puro stdlib Python, zero dipendenze pip.
Serve l'API REST e il frontend statico.
"""

import json
import os
import sqlite3
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# Aggiungi root al path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from backend.engine.motore import run_engine

CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
DB_PATH     = os.path.join(BASE_DIR, 'data', 'substmanager.db')
FRONTEND    = os.path.join(BASE_DIR, 'frontend')

# ─────────────────────────── MIME ───────────────────────────

MIME = {
    '.html': 'text/html; charset=utf-8',
    '.css':  'text/css; charset=utf-8',
    '.js':   'application/javascript; charset=utf-8',
    '.json': 'application/json',
    '.png':  'image/png',
    '.ico':  'image/x-icon',
    '.svg':  'image/svg+xml',
}

# ─────────────────────────── DB HELPER ───────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    # ── Migration automatica: crea tabelle aggiunte in versioni successive ──
    conn.execute("""CREATE TABLE IF NOT EXISTS uscite_didattiche (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        data        TEXT NOT NULL,
        classe_id   INTEGER NOT NULL REFERENCES classi(id),
        ore_json    TEXT NOT NULL DEFAULT '[1,2,3,4,5,6]',
        note        TEXT DEFAULT ''
    )""")
    conn.commit()
    return conn

def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def rows_to_list(rows):
    return [dict(r) for r in rows]

# ─────────────────────────── HANDLER ───────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Log minimale
        print(f"[{self.address_string()}] {args[0]} {args[1]}")

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, msg, code=400):
        self.send_json({'errore': msg}, code)

    def read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length:
            return json.loads(self.rfile.read(length).decode())
        return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    # ──────────── GET ────────────

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip('/')
        qs     = parse_qs(parsed.query)

        # ── API ──
        if path.startswith('/api'):
            self.handle_get_api(path, qs)
        else:
            # ── Statico ──
            self.serve_static(path)

    def handle_get_api(self, path, qs):
        conn = get_conn()
        try:
            if path == '/api/config':
                self.send_json(load_config())

            elif path == '/api/sostituzioni':
                data = qs.get('data', [date.today().isoformat()])[0]
                rows = conn.execute(
                    """SELECT s.*, da.cognome||' '||da.nome AS assente_nome,
                              ds.cognome||' '||ds.nome AS sostituto_nome,
                              c.nome AS classe_nome
                       FROM sostituzioni s
                       JOIN docenti da ON da.id=s.docente_assente_id
                       LEFT JOIN docenti ds ON ds.id=s.docente_sostituto_id
                       LEFT JOIN classi c ON c.id=s.classe_id
                       WHERE s.data=? ORDER BY s.ora""",
                    (data,)
                ).fetchall()
                self.send_json(rows_to_list(rows))

            elif path == '/api/assenze':
                data = qs.get('data', [date.today().isoformat()])[0]
                rows = conn.execute(
                    """SELECT a.*, d.cognome||' '||d.nome AS docente_nome, d.materia
                       FROM assenze a JOIN docenti d ON d.id=a.docente_id
                       WHERE a.data=? ORDER BY a.id""",
                    (data,)
                ).fetchall()
                self.send_json(rows_to_list(rows))

            elif path == '/api/docenti':
                rows = conn.execute(
                    "SELECT d.*, p.nome AS plesso_nome FROM docenti d LEFT JOIN plessi p ON p.id=d.plesso_id ORDER BY d.cognome"
                ).fetchall()
                self.send_json(rows_to_list(rows))

            elif path == '/api/disponibili':
                # Restituisce tutti i docenti con stato disponibilità per un dato giorno/ora/data
                # Un'unica query efficiente per il modal assegnazione manuale
                giorno_d = int(qs.get('giorno', [0])[0])
                ora_d    = int(qs.get('ora',    [0])[0])
                data_d   = qs.get('data', [date.today().isoformat()])[0]

                # Docenti assenti in quella data
                assenti_ids = {r[0] for r in conn.execute(
                    "SELECT docente_id FROM assenze WHERE data=?", (data_d,)
                ).fetchall()}

                # Docenti già occupati come sostituti in quella data/ora
                occupati_ids = {r[0] for r in conn.execute(
                    """SELECT docente_sostituto_id FROM sostituzioni
                       WHERE data=? AND ora=? AND stato NOT IN ('annullata')
                         AND docente_sostituto_id IS NOT NULL""",
                    (data_d, ora_d)
                ).fetchall()}

                # Docenti con lezione propria in quel giorno/ora
                con_lezione = {r[0] for r in conn.execute(
                    "SELECT docente_id FROM orario_docenti WHERE giorno=? AND ora=?",
                    (giorno_d, ora_d)
                ).fetchall()}

                # Ore eccedenti usate questa settimana
                from datetime import date as date_cls
                dt = date_cls.fromisoformat(data_d)
                sett = f"{dt.year}-W{dt.isocalendar()[1]:02d}"
                ore_ecc_usate = {r[0]: r[1] for r in conn.execute(
                    "SELECT docente_id, COUNT(*) FROM ore_eccedenti WHERE settimana=? GROUP BY docente_id",
                    (sett,)
                ).fetchall()}

                # Tutti i docenti con stato calcolato
                docenti = conn.execute(
                    "SELECT d.*, p.nome AS plesso_nome FROM docenti d LEFT JOIN plessi p ON p.id=d.plesso_id ORDER BY d.cognome"
                ).fetchall()

                result_disp = []
                for d in rows_to_list(docenti):
                    did = d['id']
                    stato = 'disponibile'
                    note  = ''
                    if did in assenti_ids:
                        stato = 'assente'
                        note  = 'Assente'
                    elif did in occupati_ids:
                        stato = 'occupato'
                        note  = 'Già assegnato come sostituto'
                    elif did in con_lezione:
                        stato = 'lezione'
                        note  = 'Ha lezione propria'

                    n_ecc = ore_ecc_usate.get(did, 0)
                    d['stato_disponibilita'] = stato
                    d['note_disponibilita']  = note
                    d['ore_eccedenti_usate'] = n_ecc
                    result_disp.append(d)

                self.send_json(result_disp)

            elif path == '/api/ore_eccedenti':
                # Riepilogo ore eccedenti per docente (settimana corrente e totale)
                from datetime import date as date_cls
                sett_param = qs.get('settimana', [None])[0]
                if not sett_param:
                    oggi = date_cls.today()
                    sett_param = f"{oggi.year}-W{oggi.isocalendar()[1]:02d}"
                rows_ecc = conn.execute(
                    """SELECT d.id, d.cognome, d.nome,
                              COUNT(CASE WHEN oe.settimana=? THEN 1 END) AS ore_sett,
                              COUNT(oe.id) AS ore_tot
                       FROM docenti d
                       LEFT JOIN ore_eccedenti oe ON oe.docente_id=d.id
                       WHERE d.disp_ore_eccedenti=1
                       GROUP BY d.id ORDER BY ore_sett DESC, ore_tot DESC, d.cognome""",
                    (sett_param,)
                ).fetchall()
                self.send_json([{
                    'id': r[0], 'cognome': r[1], 'nome': r[2],
                    'ore_settimana': r[3], 'ore_totale': r[4],
                    'settimana': sett_param
                } for r in rows_ecc])

            elif path == '/api/uscite':
                data_u = qs.get('data', [date.today().isoformat()])[0]
                rows_u = conn.execute(
                    """SELECT u.id, u.data, u.classe_id, c.nome AS classe_nome,
                              u.ore_json, u.note
                       FROM uscite_didattiche u JOIN classi c ON c.id=u.classe_id
                       WHERE u.data=? ORDER BY c.nome""",
                    (data_u,)
                ).fetchall()
                result_u = rows_to_list(rows_u)
                for r in result_u:
                    r['ore'] = json.loads(r['ore_json']) if r.get('ore_json') else []
                self.send_json(result_u)

            elif path == '/api/classi':
                rows = conn.execute(
                    "SELECT c.*, p.nome AS plesso_nome FROM classi c LEFT JOIN plessi p ON p.id=c.plesso_id ORDER BY c.nome"
                ).fetchall()
                self.send_json(rows_to_list(rows))

            elif path == '/api/compresenze':
                rows = conn.execute(
                    """SELECT cp.*, c.nome AS classe_nome,
                              d1.cognome||' '||d1.nome AS doc1_nome,
                              d2.cognome||' '||d2.nome AS doc2_nome
                       FROM compresenze cp
                       JOIN classi c ON c.id=cp.classe_id
                       JOIN docenti d1 ON d1.id=cp.docente1_id
                       JOIN docenti d2 ON d2.id=cp.docente2_id
                       ORDER BY cp.giorno, cp.ora""",
                ).fetchall()
                self.send_json(rows_to_list(rows))

            elif path == '/api/orario':
                did = qs.get('docente_id', [None])[0]
                if did:
                    rows = conn.execute(
                        """SELECT od.*, c.nome AS classe_nome
                           FROM orario_docenti od LEFT JOIN classi c ON c.id=od.classe_id
                           WHERE od.docente_id=? ORDER BY od.giorno, od.ora""",
                        (did,)
                    ).fetchall()
                    # Arricchisci con info compresenza: per ogni slot cerca i partner
                    result = []
                    for row in rows_to_list(rows):
                        cid   = row.get('classe_id')
                        giorn = row.get('giorno')
                        ora   = row.get('ora')
                        partners = []
                        if cid:
                            cp_rows = conn.execute(
                                """SELECT d.cognome||' '||d.nome AS nome, d.id
                                   FROM compresenze cp
                                   JOIN docenti d ON d.id = CASE
                                     WHEN cp.docente1_id=? THEN cp.docente2_id
                                     ELSE cp.docente1_id END
                                   WHERE cp.classe_id=? AND cp.giorno=? AND cp.ora=?
                                     AND (cp.docente1_id=? OR cp.docente2_id=?)""",
                                (int(did), cid, giorn, ora, int(did), int(did))
                            ).fetchall()
                            partners = [{'id': r[1], 'nome': r[0]} for r in cp_rows]
                        row['compresenza_partners'] = partners
                        row['ha_compresenza'] = len(partners) > 0
                        result.append(row)
                    self.send_json(result)
                else:
                    # Filtro per classe_id+giorno+ora (usato per suggerimento compresenza)
                    cid_f = qs.get('classe_id', [None])[0]
                    gior_f = qs.get('giorno', [None])[0]
                    ora_f  = qs.get('ora', [None])[0]
                    if cid_f and gior_f and ora_f:
                        rows = conn.execute(
                            """SELECT od.*, c.nome AS classe_nome, d.cognome||' '||d.nome AS docente_nome
                               FROM orario_docenti od
                               LEFT JOIN classi c ON c.id=od.classe_id
                               LEFT JOIN docenti d ON d.id=od.docente_id
                               WHERE od.classe_id=? AND od.giorno=? AND od.ora=?""",
                            (int(cid_f), int(gior_f), int(ora_f))
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            "SELECT * FROM orario_docenti ORDER BY docente_id, giorno, ora"
                        ).fetchall()
                    self.send_json(rows_to_list(rows))

            elif path == '/api/storico':
                da = qs.get('da', ['2026-01-01'])[0]
                a  = qs.get('a',  [date.today().isoformat()])[0]
                rows = conn.execute(
                    """SELECT s.*, da.cognome||' '||da.nome AS assente_nome,
                              ds.cognome||' '||ds.nome AS sostituto_nome,
                              c.nome AS classe_nome
                       FROM sostituzioni s
                       JOIN docenti da ON da.id=s.docente_assente_id
                       LEFT JOIN docenti ds ON ds.id=s.docente_sostituto_id
                       LEFT JOIN classi c ON c.id=s.classe_id
                       WHERE s.data BETWEEN ? AND ?
                       ORDER BY s.data DESC, s.ora""",
                    (da, a)
                ).fetchall()
                self.send_json(rows_to_list(rows))

            elif path == '/api/report/docenti':
                rows = conn.execute(
                    """SELECT d.id, d.cognome||' '||d.nome AS nome, d.materia,
                              COUNT(s.id) AS tot_sostituzioni,
                              SUM(CASE WHEN s.tipo='manuale' THEN 1 ELSE 0 END) AS manuali,
                              SUM(CASE WHEN oe.id IS NOT NULL THEN 1 ELSE 0 END) AS ore_ecc
                       FROM docenti d
                       LEFT JOIN sostituzioni s ON s.docente_sostituto_id=d.id AND s.stato != 'annullata'
                       LEFT JOIN ore_eccedenti oe ON oe.docente_id=d.id
                       GROUP BY d.id ORDER BY tot_sostituzioni DESC LIMIT 15""",
                ).fetchall()
                self.send_json(rows_to_list(rows))

            elif path == '/api/candidati':
                data   = qs.get('data',   [date.today().isoformat()])[0]
                ora    = int(qs.get('ora', [1])[0])
                ass_id = qs.get('assenza_id', [None])[0]
                # Trova classe dal primo slot dell'assenza
                classe_id = None
                if ass_id:
                    a_row = conn.execute("SELECT docente_id, ore_json FROM assenze WHERE id=?", (ass_id,)).fetchone()
                    if a_row:
                        from backend.engine.motore import giorno_settimana
                        g = giorno_settimana(data)
                        slot = conn.execute(
                            "SELECT classe_id FROM orario_docenti WHERE docente_id=? AND giorno=? AND ora=?",
                            (a_row['docente_id'], g, ora)
                        ).fetchone()
                        if slot:
                            classe_id = slot[0]
                self.send_json({'classe_id': classe_id, 'messaggio': 'Usa /api/engine/run per ricalcolare'})

            else:
                self.send_error_json('Endpoint non trovato', 404)

        except Exception as e:
            self.send_error_json(str(e), 500)
        finally:
            conn.close()

    # ──────────── POST ────────────

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip('/')

        conn = get_conn()
        try:
            body = self.read_body()

            if path == '/api/engine/run':
                data = body.get('data', date.today().isoformat())
                forza = bool(body.get('forza_ricalcolo', False))
                cfg  = load_config()
                result = run_engine(conn, data, cfg, forza_ricalcolo=forza)
                self.send_json(result)

            elif path == '/api/assenze':
                # Il client può mandare 'ore' (array) o 'ore_json' (stringa JSON)
                ore_raw = body.get('ore_json') or body.get('ore', [])
                if isinstance(ore_raw, str):
                    try:
                        ore_list = json.loads(ore_raw)
                    except Exception:
                        ore_list = []
                else:
                    ore_list = ore_raw if isinstance(ore_raw, list) else []
                ore_json_str = json.dumps(ore_list)

                docente_id = int(body['docente_id'])
                data_ass   = body['data']

                r = conn.execute(
                    "INSERT INTO assenze (docente_id, data, tipo, ore_json, note) VALUES (?,?,?,?,?)",
                    (docente_id, data_ass, body['tipo'], ore_json_str, body.get('note'))
                )
                ass_id = r.lastrowid

                # ── Controllo conflitti: il nuovo assente era già sostituto? ──
                # Trova le sostituzioni in quella data dove questo docente è sostituto
                # e le sue ore di assenza si sovrappongono
                conflitti = conn.execute(
                    """SELECT s.id, s.ora FROM sostituzioni s
                       WHERE s.data=? AND s.docente_sostituto_id=?
                         AND s.bloccata=0
                         AND s.stato NOT IN ('annullata','uscita_anticipata','entrata_ritardata')""",
                    (data_ass, docente_id)
                ).fetchall()

                ore_assenti = set(ore_list)
                riaperti = 0
                for sost in conflitti:
                    if sost[1] in ore_assenti:
                        # Riporta la sostituzione ad 'attesa' e rimuove il sostituto
                        conn.execute(
                            """UPDATE sostituzioni
                               SET stato='attesa', docente_sostituto_id=NULL,
                                   criterio_id=NULL, punteggio=0,
                                   motivazione='Sostituto ora assente – da riassegnare'
                               WHERE id=?""",
                            (sost[0],)
                        )
                        riaperti += 1

                conn.commit()

                # Riesegui il motore per la data (ricalcola solo gli slot 'attesa')
                rieseguito = False
                if riaperti > 0:
                    try:
                        cfg = load_config()
                        run_engine(conn, data_ass, cfg, forza_ricalcolo=False)
                        rieseguito = True
                    except Exception:
                        pass

                self.send_json({
                    'id': ass_id, 'ok': True,
                    'conflitti_riaperti': riaperti,
                    'motore_rieseguito': rieseguito
                }, 201)

            elif path == '/api/sostituzioni/manuale':
                r = conn.execute(
                    """INSERT INTO sostituzioni
                       (assenza_id, data, docente_assente_id, docente_sostituto_id,
                        classe_id, ora, tipo, stato, bloccata, motivazione, operatore)
                       VALUES (?,?,?,?,?,?,'manuale','confermata',1,?,?)""",
                    (body.get('assenza_id'), body['data'], body['docente_assente_id'],
                     body['docente_sostituto_id'], body.get('classe_id'), body['ora'],
                     body.get('motivazione', 'Assegnazione manuale'), body.get('operatore', 'vicepreside'))
                )
                conn.commit()
                self.send_json({'id': r.lastrowid, 'ok': True}, 201)

            elif path == '/api/config':
                # Patch parziale: merge sezione per sezione
                cfg = load_config()
                for k, v in body.items():
                    if isinstance(v, dict) and k in cfg and isinstance(cfg[k], dict):
                        cfg[k].update(v)
                    else:
                        cfg[k] = v
                save_config(cfg)
                self.send_json({'ok': True})

            elif path == '/api/orario':
                # Crea/aggiorna singolo slot orario + ricalcola compresenza automatica
                did       = int(body['docente_id'])
                giorno    = int(body['giorno'])
                ora       = int(body['ora'])
                tipo      = body.get('tipo', 'lezione')
                classe_id = body.get('classe_id')
                materia   = body.get('materia', '')
                if classe_id:
                    classe_id = int(classe_id)

                # Salva/aggiorna lo slot
                ex = conn.execute(
                    "SELECT id FROM orario_docenti WHERE docente_id=? AND giorno=? AND ora=?",
                    (did, giorno, ora)
                ).fetchone()
                if ex:
                    conn.execute(
                        "UPDATE orario_docenti SET classe_id=?, tipo=?, materia=? WHERE id=?",
                        (classe_id, tipo, materia, ex[0])
                    )
                    slot_id = ex[0]
                else:
                    r = conn.execute(
                        "INSERT INTO orario_docenti (docente_id, classe_id, giorno, ora, tipo, materia) "
                        "VALUES (?,?,?,?,?,?)",
                        (did, classe_id, giorno, ora, tipo, materia)
                    )
                    slot_id = r.lastrowid

                # ── Rilevamento automatico compresenza ──
                # Se c'è una classe, cerca altri docenti nello stesso slot
                compresenze_trovate = []
                if classe_id:
                    altri = conn.execute(
                        """SELECT od.docente_id FROM orario_docenti od
                           WHERE od.classe_id=? AND od.giorno=? AND od.ora=?
                             AND od.docente_id != ?""",
                        (classe_id, giorno, ora, did)
                    ).fetchall()
                    for (altro_id,) in altri:
                        d1 = min(did, altro_id)
                        d2 = max(did, altro_id)
                        ex_cp = conn.execute(
                            "SELECT id FROM compresenze WHERE classe_id=? AND giorno=? AND ora=? "
                            "AND docente1_id=? AND docente2_id=?",
                            (classe_id, giorno, ora, d1, d2)
                        ).fetchone()
                        if not ex_cp:
                            conn.execute(
                                "INSERT INTO compresenze (classe_id, giorno, ora, docente1_id, docente2_id, note) "
                                "VALUES (?,?,?,?,?,'manuale')",
                                (classe_id, giorno, ora, d1, d2)
                            )
                            compresenze_trovate.append(altro_id)

                conn.commit()
                self.send_json({
                    'id': slot_id, 'ok': True,
                    'compresenze_create': len(compresenze_trovate),
                    'partner_ids': compresenze_trovate
                }, 200 if ex else 201)

            elif path == '/api/uscite':
                # Registra uscita didattica per una classe in una data
                classe_id_u = int(body['classe_id'])
                data_u      = body['data']
                ore_u       = body.get('ore', [1,2,3,4,5,6])
                note_u      = body.get('note', '')
                import json as _json
                ore_json_u  = _json.dumps(sorted(ore_u)) if isinstance(ore_u, list) else ore_u
                # Evita duplicati
                ex_u = conn.execute(
                    "SELECT id FROM uscite_didattiche WHERE data=? AND classe_id=?",
                    (data_u, classe_id_u)
                ).fetchone()
                if ex_u:
                    conn.execute(
                        "UPDATE uscite_didattiche SET ore_json=?, note=? WHERE id=?",
                        (ore_json_u, note_u, ex_u[0])
                    )
                    conn.commit()
                    self.send_json({'id': ex_u[0], 'ok': True, 'updated': True})
                else:
                    r_u = conn.execute(
                        "INSERT INTO uscite_didattiche (data, classe_id, ore_json, note) VALUES (?,?,?,?)",
                        (data_u, classe_id_u, ore_json_u, note_u)
                    )
                    conn.commit()
                    self.send_json({'id': r_u.lastrowid, 'ok': True}, 201)

            elif path == '/api/docenti':
                # Crea nuovo docente
                cognome = (body.get('cognome') or '').strip().upper()
                nome    = (body.get('nome')    or '').strip().upper()
                if not cognome:
                    self.send_error_json('Cognome obbligatorio', 400)
                    return
                r = conn.execute(
                    """INSERT INTO docenti
                       (cognome, nome, materia, ruolo, plesso_id,
                        ore_cattedra, disp_ore_eccedenti, escluso_motore, note)
                       VALUES (?,?,?,?,?,?,?,0,?)""",
                    (cognome, nome,
                     (body.get('materia') or '').strip(),
                     body.get('ruolo', 'curriculare'),
                     int(body.get('plesso_id', 1)),
                     int(body.get('ore_cattedra', 18)),
                     1 if body.get('disp_ore_eccedenti') else 0,
                     body.get('note', ''))
                )
                conn.commit()
                self.send_json({'id': r.lastrowid, 'ok': True}, 201)

            elif path == '/api/criteri':
                # Aggiungi criterio custom
                import time
                cfg = load_config()
                nid = 'custom_' + body.get('nome','x').lower().replace(' ','') + '_' + str(int(time.time()))[:8]
                nuovo = {
                    'id': nid,
                    'nome': body['nome'],
                    'descrizione': body.get('descrizione', ''),
                    'attivo': True,
                    'priorita': len(cfg['criteri']) + len(cfg.get('criteri_custom',[])) + 1,
                    'rimuovibile': True,
                    'colore': body.get('colore', '#888888'),
                    'parametri': body.get('parametri', {})
                }
                cfg.setdefault('criteri_custom', []).append(nuovo)
                save_config(cfg)
                self.send_json({'id': nid, 'ok': True}, 201)

            else:
                self.send_error_json('Endpoint non trovato', 404)

        except Exception as e:
            self.send_error_json(str(e), 500)
        finally:
            conn.close()

    # ──────────── PUT ────────────

    def do_PUT(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip('/')

        conn = get_conn()
        try:
            body = self.read_body()

            if path == '/api/criteri':
                # Salva array completo di criteri (riordino / toggle)
                cfg = load_config()
                criteri_in = body  # lista completa
                builtin_ids = {c['id'] for c in cfg['criteri']}
                cfg['criteri'] = [c for c in criteri_in if c['id'] in builtin_ids]
                cfg['criteri_custom'] = [c for c in criteri_in if c['id'] not in builtin_ids]
                save_config(cfg)
                self.send_json({'ok': True})

            elif path.startswith('/api/sostituzioni/'):
                sid = path.split('/')[-1]
                allowed = {'stato', 'docente_sostituto_id', 'bloccata', 'motivazione', 'tipo'}
                updates = {k: v for k, v in body.items() if k in allowed}
                # Se si assegna un sostituto manualmente → tipo=manuale, bloccata=1, stato=confermata
                if 'docente_sostituto_id' in updates and updates['docente_sostituto_id']:
                    updates.setdefault('tipo', 'manuale')
                    updates.setdefault('bloccata', 1)
                    updates.setdefault('stato', 'confermata')
                # Se si rimuove il sostituto → riporta ad attesa
                if 'docente_sostituto_id' in updates and not updates['docente_sostituto_id']:
                    updates['stato'] = 'attesa'
                    updates['tipo']  = 'auto'
                    updates['bloccata'] = 0
                if updates:
                    sets = ', '.join(f"{k}=?" for k in updates)
                    conn.execute(f"UPDATE sostituzioni SET {sets} WHERE id=?",
                                 list(updates.values()) + [sid])
                    conn.commit()
                self.send_json({'ok': True})

            elif path.startswith('/api/docenti/'):
                did = path.split('/')[-1]
                allowed = {'materia', 'ruolo', 'plesso_id', 'disp_ore_eccedenti', 'escluso_motore', 'note'}
                updates = {k: v for k, v in body.items() if k in allowed}
                if updates:
                    sets = ', '.join(f"{k}=?" for k in updates)
                    conn.execute(f"UPDATE docenti SET {sets} WHERE id=?",
                                 list(updates.values()) + [did])
                    conn.commit()
                self.send_json({'ok': True})

            else:
                self.send_error_json('Endpoint non trovato', 404)

        except Exception as e:
            self.send_error_json(str(e), 500)
        finally:
            conn.close()

    # ──────────── DELETE ────────────

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip('/')

        conn = get_conn()
        try:
            if path.startswith('/api/sostituzioni/'):
                sid = path.split('/')[-1]
                # Leggi la data per il ricalcolo
                row = conn.execute(
                    "SELECT data, assenza_id, bloccata FROM sostituzioni WHERE id=?", (sid,)
                ).fetchone()
                if row and row[2]:  # bloccata=1 → non si può rimuovere
                    self.send_error_json('Sostituzione bloccata: prima sblocca', 403)
                    return
                data_sost = row[0] if row else None
                # Rimuove ore_eccedenti collegata (FK)
                conn.execute("DELETE FROM ore_eccedenti WHERE sostituzione_id=?", (sid,))
                # Riporta la sostituzione ad 'attesa' (così il motore può ricoprirla)
                conn.execute(
                    """UPDATE sostituzioni
                       SET stato='attesa', docente_sostituto_id=NULL, tipo='auto',
                           criterio_id=NULL, punteggio=0, bloccata=0,
                           motivazione='Sostituzione rimossa – da riassegnare'
                       WHERE id=?""",
                    (sid,)
                )
                conn.commit()
                # Riesegui il motore per ricoprire lo slot (solo gli 'attesa')
                if data_sost:
                    try:
                        from backend.engine.motore import run_engine
                        cfg = load_config()
                        run_engine(conn, data_sost, cfg, forza_ricalcolo=False)
                    except Exception:
                        pass
                self.send_json({'ok': True})

            elif path.startswith('/api/assenze/'):
                aid = path.split('/')[-1]

                # Leggi la data dell'assenza prima di cancellarla (serve per ricalcolo)
                ass_row = conn.execute(
                    "SELECT data, docente_id FROM assenze WHERE id=?", (aid,)
                ).fetchone()
                data_ass = ass_row[0] if ass_row else None
                doc_id   = ass_row[1] if ass_row else None

                # Trova i docenti che erano sostituti di questa assenza
                # (potrebbero essere liberati per coprire altri slot in attesa)
                ex_sostituti = {r[0] for r in conn.execute(
                    "SELECT DISTINCT docente_sostituto_id FROM sostituzioni "
                    "WHERE assenza_id=? AND docente_sostituto_id IS NOT NULL", (aid,)
                ).fetchall()}

                # Cancella ore_eccedenti collegate (FK)
                conn.execute(
                    "DELETE FROM ore_eccedenti WHERE sostituzione_id IN "
                    "(SELECT id FROM sostituzioni WHERE assenza_id=?)", (aid,)
                )
                # Cancella le sostituzioni di questa assenza
                conn.execute("DELETE FROM sostituzioni WHERE assenza_id=?", (aid,))
                conn.execute("DELETE FROM assenze WHERE id=?", (aid,))
                conn.commit()

                # Ricalcola: per quella data potrebbero esserci slot in 'attesa'
                # che ora possono essere coperti dagli ex-sostituti diventati liberi.
                # Eseguiamo il motore in modalità normale (non forzata):
                # coprirà solo gli slot ancora in 'attesa'.
                ricalcolato = False
                if data_ass:
                    try:
                        cfg = load_config()
                        run_engine(conn, data_ass, cfg, forza_ricalcolo=False)
                        ricalcolato = True
                    except Exception:
                        pass

                self.send_json({'ok': True, 'ricalcolato': ricalcolato})

            elif path.startswith('/api/uscite/'):
                uid = path.split('/')[-1]
                conn.execute("DELETE FROM uscite_didattiche WHERE id=?", (uid,))
                conn.commit()
                self.send_json({'ok': True})

            elif path == '/api/docenti':
                # Elimina TUTTI i docenti e i dati collegati
                conn.execute("DELETE FROM orario_docenti")
                conn.execute("DELETE FROM compresenze")
                conn.execute("DELETE FROM permessi_recupero")
                conn.execute("DELETE FROM alunni_h")
                conn.execute("DELETE FROM ore_eccedenti")
                conn.execute("DELETE FROM sostituzioni")
                conn.execute("DELETE FROM assenze")
                conn.execute("DELETE FROM docenti")
                conn.commit()
                self.send_json({'ok': True, 'messaggio': 'Tutti i docenti eliminati'})

            elif path.startswith('/api/docenti/'):
                did = path.split('/')[-1]
                # Elimina dati collegati al docente
                conn.execute("DELETE FROM orario_docenti WHERE docente_id=?", (did,))
                conn.execute("DELETE FROM permessi_recupero WHERE docente_id=?", (did,))
                conn.execute("DELETE FROM ore_eccedenti WHERE docente_id=?", (did,))
                conn.execute("DELETE FROM alunni_h WHERE docente_sostegno_id=?", (did,))
                # Compresenze dove è coinvolto
                conn.execute("DELETE FROM compresenze WHERE docente1_id=? OR docente2_id=?", (did, did))
                # Assenze e sostituzioni: mantieni lo storico, metti NULL dove necessario
                conn.execute("UPDATE sostituzioni SET docente_sostituto_id=NULL WHERE docente_sostituto_id=?", (did,))
                conn.execute("UPDATE sostituzioni SET stato='annullata' WHERE docente_assente_id=?", (did,))
                conn.execute("DELETE FROM assenze WHERE docente_id=?", (did,))
                conn.execute("DELETE FROM docenti WHERE id=?", (did,))
                conn.commit()
                self.send_json({'ok': True})

            elif path.startswith('/api/orario/'):
                oid = path.split('/')[-1]
                # Prima leggi lo slot per sapere docente/classe/giorno/ora
                slot = conn.execute(
                    "SELECT docente_id, classe_id, giorno, ora FROM orario_docenti WHERE id=?", (oid,)
                ).fetchone()
                conn.execute("DELETE FROM orario_docenti WHERE id=?", (oid,))
                # Rimuovi le compresenze in cui era coinvolto questo docente in quello slot
                if slot:
                    did, cid, giorno, ora = slot
                    conn.execute(
                        "DELETE FROM compresenze WHERE classe_id=? AND giorno=? AND ora=? "
                        "AND (docente1_id=? OR docente2_id=?)",
                        (cid, giorno, ora, did, did)
                    )
                conn.commit()
                self.send_json({'ok': True})

            elif path.startswith('/api/criteri/'):
                cid = path.split('/')[-1]
                cfg = load_config()
                cfg['criteri_custom'] = [c for c in cfg.get('criteri_custom', []) if c['id'] != cid]
                save_config(cfg)
                self.send_json({'ok': True})

            else:
                self.send_error_json('Endpoint non trovato', 404)

        except Exception as e:
            self.send_error_json(str(e), 500)
        finally:
            conn.close()

    # ──────────── STATICO ────────────

    def serve_static(self, path):
        if path == '' or path == '/':
            path = '/index.html'
        file_path = os.path.join(FRONTEND, path.lstrip('/'))
        if not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'404 Not Found')
            return
        ext = os.path.splitext(file_path)[1]
        mime = MIME.get(ext, 'application/octet-stream')
        with open(file_path, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', len(data))
        self.end_headers()
        self.wfile.write(data)


# ─────────────────────────── AVVIO ───────────────────────────

if __name__ == '__main__':
    cfg = {}
    try:
        cfg = json.load(open(CONFIG_PATH))
    except Exception:
        pass
    porta = cfg.get('sistema', {}).get('porta', 8080)

    print(f"""
╔══════════════════════════════════════════════╗
║         SubstManager v2.0  –  avvio          ║
║  Database : {DB_PATH[-35:]:35s}  ║
║  Frontend : http://localhost:{porta:<5d}             ║
╚══════════════════════════════════════════════╝
""")
    server = HTTPServer(('0.0.0.0', porta), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[✓] Server fermato.")
