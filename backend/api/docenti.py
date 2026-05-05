"""SubstManager · API Docenti"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
from db.database import get_db, rows_to_list

router = APIRouter()


class DocenteCreate(BaseModel):
    cognome: str
    nome: str
    ruolo: str   # curriculare | sostegno | potenziamento
    plesso_id: Optional[int] = 1
    ore_cattedra: int = 18
    disp_eccedenti: bool = False
    max_eccedenti_sett: int = 6
    email: Optional[str] = None
    note: Optional[str] = None
    materie_ids: List[int] = []


@router.get("/")
def lista_docenti(
    ruolo: Optional[str] = None,
    plesso_id: Optional[int] = None,
    conn: sqlite3.Connection = Depends(get_db)
):
    q = """SELECT d.*,
                  p.nome as plesso_nome,
                  (SELECT GROUP_CONCAT(m.nome, ', ')
                   FROM docente_materie dm JOIN materie m ON m.id=dm.materia_id
                   WHERE dm.docente_id=d.id) as materie
           FROM docenti d LEFT JOIN plessi p ON p.id=d.plesso_id
           WHERE d.attivo=1"""
    params = []
    if ruolo: q += " AND d.ruolo=?"; params.append(ruolo)
    if plesso_id: q += " AND d.plesso_id=?"; params.append(plesso_id)
    q += " ORDER BY d.cognome, d.nome"
    return rows_to_list(conn.execute(q, params).fetchall())


@router.get("/{docente_id}")
def get_docente(docente_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute(
        "SELECT * FROM docenti WHERE id=?", (docente_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Docente non trovato")
    return dict(row)


@router.post("/", status_code=201)
def crea_docente(body: DocenteCreate, conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute(
        """INSERT INTO docenti
           (cognome,nome,ruolo,plesso_id,ore_cattedra,disp_eccedenti,
            max_eccedenti_sett,email,note)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (body.cognome, body.nome, body.ruolo, body.plesso_id, body.ore_cattedra,
         int(body.disp_eccedenti), body.max_eccedenti_sett, body.email, body.note)
    )
    doc_id = cur.lastrowid
    for m_id in body.materie_ids:
        conn.execute(
            "INSERT OR IGNORE INTO docente_materie VALUES (?,?)", (doc_id, m_id)
        )
    return {"id": doc_id, "message": "Docente creato"}


@router.delete("/{docente_id}")
def disattiva_docente(docente_id: int, conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("UPDATE docenti SET attivo=0 WHERE id=?", (docente_id,))
    return {"message": "Docente disattivato"}


@router.get("/{docente_id}/ore-settimana")
def ore_settimana_docente(
    docente_id: int, settimana: str, conn: sqlite3.Connection = Depends(get_db)
):
    """Ore eccedenti usate in una settimana ISO (es. 2026-W18)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(ore),0) as tot FROM ore_eccedenti WHERE docente_id=? AND settimana=?",
        (docente_id, settimana)
    ).fetchone()
    return {"settimana": settimana, "ore_eccedenti": row[0]}
