"""Supplentia · API Assenze"""

import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import sqlite3

from db.database import get_db, rows_to_list, row_to_dict
from core.motore import genera_sostituzioni_assenza

router = APIRouter()


class AssenzaCreate(BaseModel):
    docente_id: int
    data: str           # ISO: 2026-04-30
    tipo: str           # malattia | permesso_breve | ferie | aggiornamento | altro
    ore: List[int]      # [1, 2, 3]
    certificato: bool = False
    note: Optional[str] = None


class AssenzaUpdate(BaseModel):
    tipo: Optional[str] = None
    ore: Optional[List[int]] = None
    certificato: Optional[bool] = None
    note: Optional[str] = None


@router.get("/")
def lista_assenze(
    data: Optional[str] = None,
    docente_id: Optional[int] = None,
    conn: sqlite3.Connection = Depends(get_db)
):
    q = """
        SELECT a.*, d.cognome, d.nome as docente_nome,
               d.ruolo as docente_ruolo
        FROM assenze a
        JOIN docenti d ON d.id = a.docente_id
        WHERE 1=1
    """
    params = []
    if data:
        q += " AND a.data=?"
        params.append(data)
    if docente_id:
        q += " AND a.docente_id=?"
        params.append(docente_id)
    q += " ORDER BY a.data DESC, a.id DESC"

    rows = conn.execute(q, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['ore'] = json.loads(d['ore'])
        result.append(d)
    return result


@router.get("/{assenza_id}")
def get_assenza(assenza_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute(
        """SELECT a.*, d.cognome, d.nome as docente_nome
           FROM assenze a JOIN docenti d ON d.id=a.docente_id
           WHERE a.id=?""",
        (assenza_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Assenza non trovata")
    d = dict(row)
    d['ore'] = json.loads(d['ore'])
    return d


@router.post("/", status_code=201)
def crea_assenza(body: AssenzaCreate, conn: sqlite3.Connection = Depends(get_db)):
    # Validazione tipo
    tipi_validi = ('malattia', 'permesso_breve', 'ferie', 'aggiornamento', 'altro')
    if body.tipo not in tipi_validi:
        raise HTTPException(400, f"Tipo non valido. Valori: {tipi_validi}")

    # Verifica docente esiste
    if not conn.execute("SELECT id FROM docenti WHERE id=?", (body.docente_id,)).fetchone():
        raise HTTPException(404, "Docente non trovato")

    cur = conn.execute(
        """INSERT INTO assenze (docente_id, data, tipo, ore, certificato, note)
           VALUES (?,?,?,?,?,?)""",
        (body.docente_id, body.data, body.tipo,
         json.dumps(sorted(body.ore)), int(body.certificato), body.note)
    )
    assenza_id = cur.lastrowid

    # Se permesso breve: crea debito
    if body.tipo == 'permesso_breve':
        conn.execute(
            "INSERT INTO permessi_brevi (docente_id, assenza_id, ore_debito) VALUES (?,?,?)",
            (body.docente_id, assenza_id, len(body.ore))
        )

    conn.commit()

    # Esegui il motore automaticamente
    try:
        risultati = genera_sostituzioni_assenza(conn, assenza_id)
        conn.commit()
    except Exception as e:
        risultati = []

    return {
        "id": assenza_id,
        "message": "Assenza registrata",
        "sostituzioni_generate": len(risultati),
        "sostituzioni": risultati
    }


@router.put("/{assenza_id}")
def aggiorna_assenza(
    assenza_id: int, body: AssenzaUpdate,
    conn: sqlite3.Connection = Depends(get_db)
):
    if not conn.execute("SELECT id FROM assenze WHERE id=?", (assenza_id,)).fetchone():
        raise HTTPException(404, "Assenza non trovata")
    updates, values = [], []
    if body.tipo: updates.append("tipo=?"); values.append(body.tipo)
    if body.ore is not None: updates.append("ore=?"); values.append(json.dumps(body.ore))
    if body.certificato is not None: updates.append("certificato=?"); values.append(int(body.certificato))
    if body.note is not None: updates.append("note=?"); values.append(body.note)
    if updates:
        values.append(assenza_id)
        conn.execute(f"UPDATE assenze SET {', '.join(updates)} WHERE id=?", values)
    return {"message": "Aggiornata"}


@router.delete("/{assenza_id}")
def elimina_assenza(assenza_id: int, conn: sqlite3.Connection = Depends(get_db)):
    if not conn.execute("SELECT id FROM assenze WHERE id=?", (assenza_id,)).fetchone():
        raise HTTPException(404, "Assenza non trovata")
    conn.execute("DELETE FROM assenze WHERE id=?", (assenza_id,))
    return {"message": "Eliminata"}


@router.post("/{assenza_id}/rigenera")
def rigenera_sostituzioni(
    assenza_id: int, conn: sqlite3.Connection = Depends(get_db)
):
    """Riesegue il motore per una specifica assenza."""
    if not conn.execute("SELECT id FROM assenze WHERE id=?", (assenza_id,)).fetchone():
        raise HTTPException(404, "Assenza non trovata")
    risultati = genera_sostituzioni_assenza(conn, assenza_id)
    conn.commit()
    return {"sostituzioni": risultati}
