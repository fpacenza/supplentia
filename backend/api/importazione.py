"""
Supplentia · API Importazione Orario
Supporta CSV generico e formato Argo/Axios.

Formato CSV atteso (separatore ; o ,):
  cognome;nome;classe;materia;giorno;ora;tipo
  Bianchi;Marco;3A;Informatica;1;1;normale
  De Luca;Mario;3A;TEC;1;1;compresenza

Il campo `tipo` può essere: normale | potenziamento | compresenza | sostegno
Le compresenze vengono rilevate automaticamente: stessa classe/giorno/ora = compresenza.
"""

import csv, io, json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import sqlite3
from db.database import get_db

router = APIRouter()

GIORNI_MAP = {
    'lun': 1, 'lunedì': 1, 'lunedi': 1, 'mon': 1, 'monday': 1,
    'mar': 2, 'martedì': 2, 'martedi': 2, 'tue': 2, 'tuesday': 2,
    'mer': 3, 'mercoledì': 3, 'mercoledi': 3, 'wed': 3, 'wednesday': 3,
    'gio': 4, 'giovedì': 4, 'giovedi': 4, 'thu': 4, 'thursday': 4,
    'ven': 5, 'venerdì': 5, 'venerdi': 5, 'fri': 5, 'friday': 5,
    'sab': 6, 'sabato': 6, 'sat': 6, 'saturday': 6,
}


def _parse_giorno(val: str) -> int:
    v = val.strip().lower()
    if v.isdigit():
        return int(v)
    return GIORNI_MAP.get(v, 0)


def _get_or_create_docente(conn, cognome: str, nome: str, ruolo: str = 'curriculare') -> int:
    row = conn.execute(
        "SELECT id FROM docenti WHERE cognome=? AND nome=?", (cognome.strip(), nome.strip())
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO docenti (cognome,nome,ruolo,plesso_id,ore_cattedra) VALUES (?,?,'curriculare',1,18)",
        (cognome.strip(), nome.strip())
    )
    return cur.lastrowid


def _get_or_create_classe(conn, nome: str) -> int:
    row = conn.execute("SELECT id FROM classi WHERE nome=?", (nome.strip(),)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO classi (nome, plesso_id) VALUES (?,1)", (nome.strip(),)
    )
    return cur.lastrowid


def _get_or_create_materia(conn, nome: str) -> int:
    row = conn.execute("SELECT id FROM materie WHERE nome=?", (nome.strip(),)).fetchone()
    if row:
        return row[0]
    codice = nome.strip()[:6].upper()
    cur = conn.execute(
        "INSERT INTO materie (codice, nome) VALUES (?,?)", (codice, nome.strip())
    )
    return cur.lastrowid


@router.post("/csv")
async def importa_csv(
    file: UploadFile = File(...),
    anno_scolastico: str = "2025/2026",
    sovrascrivi: bool = False,
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Importa orario da file CSV.
    Riconosce automaticamente le compresenze (stessa classe/giorno/ora).
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(400, "File deve essere CSV")

    content = await file.read()
    try:
        text = content.decode('utf-8-sig')  # gestisce BOM
    except UnicodeDecodeError:
        text = content.decode('latin-1')

    # Sniff del separatore
    dialect = csv.Sniffer().sniff(text[:2048], delimiters=',;\t')
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)

    if sovrascrivi:
        conn.execute("DELETE FROM compresenze")
        conn.execute("DELETE FROM orario WHERE anno_scolastico=?", (anno_scolastico,))

    inseriti = 0
    errori = []
    # Mappa (classe_id, giorno, ora) -> [orario_id] per rilevare compresenze
    slot_map: dict = {}

    for i, row in enumerate(reader, start=2):
        try:
            # Normalizza chiavi
            r = {k.lower().strip(): v.strip() for k, v in row.items()}

            cognome = r.get('cognome') or r.get('docente_cognome', '')
            nome_doc = r.get('nome') or r.get('docente_nome', '')
            nome_classe = r.get('classe') or r.get('classe_nome', '')
            nome_materia = r.get('materia') or r.get('materia_nome', '')
            giorno_raw = r.get('giorno', '0')
            ora_raw = r.get('ora', '0')
            tipo = r.get('tipo', 'normale').lower()

            giorno = _parse_giorno(giorno_raw)
            ora = int(ora_raw)

            if not cognome or not nome_classe or giorno == 0 or ora == 0:
                errori.append(f"Riga {i}: dati incompleti {r}")
                continue

            doc_id = _get_or_create_docente(conn, cognome, nome_doc)
            classe_id = _get_or_create_classe(conn, nome_classe)
            mat_id = _get_or_create_materia(conn, nome_materia) if nome_materia else None

            cur = conn.execute(
                """INSERT INTO orario
                   (docente_id, classe_id, materia_id, giorno, ora, tipo, anno_scolastico)
                   VALUES (?,?,?,?,?,?,?)""",
                (doc_id, classe_id, mat_id, giorno, ora, tipo, anno_scolastico)
            )
            oid = cur.lastrowid
            inseriti += 1

            # Rileva compresenze
            key = (classe_id, giorno, ora)
            if key in slot_map:
                # È una compresenza! Aggiorna tipo e crea link
                existing_oid = slot_map[key]
                conn.execute(
                    "UPDATE orario SET tipo='compresenza' WHERE id IN (?,?)",
                    (existing_oid, oid)
                )
                conn.execute(
                    "INSERT OR IGNORE INTO compresenze (orario_id_1, orario_id_2, note) VALUES (?,?,?)",
                    (existing_oid, oid, f"Rilevata automaticamente dall'importazione")
                )
            else:
                slot_map[key] = oid

        except Exception as e:
            errori.append(f"Riga {i}: {str(e)}")
            continue

    conn.commit()

    return {
        "message": f"Importazione completata",
        "righe_importate": inseriti,
        "compresenze_rilevate": sum(1 for v in slot_map.values() if isinstance(v, int)) - inseriti + len(slot_map),
        "errori": errori[:20],  # max 20 errori nel response
    }


@router.get("/template-csv")
def scarica_template():
    """Restituisce intestazioni CSV di esempio."""
    return {
        "formato": "CSV con separatore ;",
        "colonne": ["cognome", "nome", "classe", "materia", "giorno", "ora", "tipo"],
        "valori_giorno": "1=Lun, 2=Mar, 3=Mer, 4=Gio, 5=Ven, 6=Sab",
        "valori_tipo": "normale | potenziamento | compresenza | sostegno",
        "esempio": [
            "Bianchi;Marco;3A;Informatica;1;1;normale",
            "De Luca;Mario;3A;TEC;1;1;compresenza",
            "Esposito;Roberta;3B;Informatica;2;3;potenziamento",
            "Fontana;Elena;3B;Sostegno;3;1;sostegno",
        ]
    }
