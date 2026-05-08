"""SubstManager · API Sostituzioni"""

import json
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import Optional
import sqlite3
from db.database import get_db, rows_to_list

router = APIRouter()


class SostituzioneManuale(BaseModel):
    assenza_id: int
    docente_sost_id: int
    classe_id: int
    data: str
    ora: int
    bloccata: bool = True
    note_manuale: Optional[str] = None


@router.get("/")
def lista_sostituzioni(
    data: Optional[str] = None,
    docente_sost_id: Optional[int] = None,
    stato: Optional[str] = None,
    conn: sqlite3.Connection = Depends(get_db)
):
    q = """
        SELECT s.*,
               ds.cognome || ' ' || ds.nome as docente_sost_nome,
               da.cognome || ' ' || da.nome as docente_assente_nome,
               c.nome as classe_nome,
               cr.nome as criterio_nome
        FROM sostituzioni s
        LEFT JOIN docenti ds ON ds.id = s.docente_sost_id
        LEFT JOIN assenze a ON a.id = s.assenza_id
        LEFT JOIN docenti da ON da.id = a.docente_id
        LEFT JOIN classi c ON c.id = s.classe_id
        LEFT JOIN criteri cr ON cr.id = s.criterio_id
        WHERE 1=1
    """
    params = []
    if data:
        q += " AND s.data=?"; params.append(data)
    if docente_sost_id:
        q += " AND s.docente_sost_id=?"; params.append(docente_sost_id)
    if stato:
        q += " AND s.stato=?"; params.append(stato)
    q += " ORDER BY s.data DESC, s.ora ASC"
    return rows_to_list(conn.execute(q, params).fetchall())


@router.post("/manuale", status_code=201)
def assegna_manuale(body: SostituzioneManuale, conn: sqlite3.Connection = Depends(get_db)):
    # Cancella eventuale automatica non bloccata per stessa ora/assenza
    conn.execute(
        """DELETE FROM sostituzioni
           WHERE assenza_id=? AND ora=? AND tipo='automatica' AND bloccata=0""",
        (body.assenza_id, body.ora)
    )
    cur = conn.execute(
        """INSERT INTO sostituzioni
           (assenza_id, docente_sost_id, classe_id, data, ora,
            tipo, bloccata, stato, note_manuale)
           VALUES (?,?,?,?,?,'manuale',?,  'confermata',?)""",
        (body.assenza_id, body.docente_sost_id, body.classe_id,
         body.data, body.ora, int(body.bloccata), body.note_manuale)
    )
    return {"id": cur.lastrowid, "message": "Sostituzione manuale confermata"}


@router.patch("/{sost_id}/blocca")
def blocca_sostituzione(sost_id: int, conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("UPDATE sostituzioni SET bloccata=1 WHERE id=?", (sost_id,))
    return {"message": "Bloccata"}


@router.patch("/{sost_id}/sblocca")
def sblocca_sostituzione(sost_id: int, conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("UPDATE sostituzioni SET bloccata=0 WHERE id=?", (sost_id,))
    return {"message": "Sbloccata"}


@router.delete("/{sost_id}")
def elimina_sostituzione(sost_id: int, conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("DELETE FROM sostituzioni WHERE id=?", (sost_id,))
    return {"message": "Eliminata"}


@router.get("/settimana/{data_iso}")
def sostituzioni_settimana(data_iso: str, conn: sqlite3.Connection = Depends(get_db)):
    """Sostituzioni per l'intera settimana contenente la data."""
    from datetime import date, timedelta
    d = date.fromisoformat(data_iso)
    lun = d - timedelta(days=d.weekday())
    ven = lun + timedelta(days=4)
    rows = conn.execute(
        """SELECT s.*, ds.cognome||' '||ds.nome as sost_nome,
                  c.nome as classe_nome, cr.codice as criterio_codice
           FROM sostituzioni s
           LEFT JOIN docenti ds ON ds.id=s.docente_sost_id
           LEFT JOIN classi c ON c.id=s.classe_id
           LEFT JOIN criteri cr ON cr.id=s.criterio_id
           WHERE s.data BETWEEN ? AND ?
           ORDER BY s.data, s.ora""",
        (lun.isoformat(), ven.isoformat())
    ).fetchall()
    return rows_to_list(rows)
