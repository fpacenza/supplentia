"""Supplentia · API Orario e Compresenze"""

import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
import sqlite3, csv, io

from db.database import get_db, rows_to_list

router = APIRouter()


class OrarioEntry(BaseModel):
    docente_id: int
    classe_id: int
    materia_id: Optional[int] = None
    giorno: int     # 1=Lun ... 5=Ven
    ora: int        # 1-8
    tipo: str = "normale"   # normale|potenziamento|compresenza|sostegno
    anno_scolastico: str = "2025/2026"


class CompresenzaCreate(BaseModel):
    orario_id_1: int
    orario_id_2: int
    note: Optional[str] = None


# ── Orario ────────────────────────────────────────────────────

@router.get("/docente/{docente_id}")
def orario_docente(docente_id: int, conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        """SELECT o.*, c.nome as classe_nome, m.nome as materia_nome
           FROM orario o
           JOIN classi c ON c.id=o.classe_id
           LEFT JOIN materie m ON m.id=o.materia_id
           WHERE o.docente_id=?
           ORDER BY o.giorno, o.ora""",
        (docente_id,)
    ).fetchall()
    return rows_to_list(rows)


@router.get("/classe/{classe_id}")
def orario_classe(classe_id: int, conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        """SELECT o.*, d.cognome||' '||d.nome as docente_nome, m.nome as materia_nome
           FROM orario o
           JOIN docenti d ON d.id=o.docente_id
           LEFT JOIN materie m ON m.id=o.materia_id
           WHERE o.classe_id=?
           ORDER BY o.giorno, o.ora""",
        (classe_id,)
    ).fetchall()
    return rows_to_list(rows)


@router.get("/giorno/{giorno}/ora/{ora}")
def docenti_liberi(giorno: int, ora: int, conn: sqlite3.Connection = Depends(get_db)):
    """Docenti che non hanno lezione in quel giorno/ora."""
    rows = conn.execute(
        """SELECT d.id, d.cognome, d.nome, d.ruolo, d.disp_eccedenti
           FROM docenti d
           WHERE d.attivo=1
             AND d.id NOT IN (
                 SELECT docente_id FROM orario
                 WHERE giorno=? AND ora=?
             )
           ORDER BY d.cognome""",
        (giorno, ora)
    ).fetchall()
    return rows_to_list(rows)


@router.post("/", status_code=201)
def aggiungi_slot(body: OrarioEntry, conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute(
        """INSERT INTO orario (docente_id,classe_id,materia_id,giorno,ora,tipo,anno_scolastico)
           VALUES (?,?,?,?,?,?,?)""",
        (body.docente_id, body.classe_id, body.materia_id, body.giorno,
         body.ora, body.tipo, body.anno_scolastico)
    )
    return {"id": cur.lastrowid}


@router.delete("/{orario_id}")
def rimuovi_slot(orario_id: int, conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("DELETE FROM orario WHERE id=?", (orario_id,))
    return {"message": "Rimosso"}


# ── Compresenze ───────────────────────────────────────────────

@router.get("/compresenze")
def lista_compresenze(conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        """SELECT cp.*,
                  o1.docente_id as doc1_id, d1.cognome||' '||d1.nome as doc1_nome,
                  o1.classe_id, cl.nome as classe_nome,
                  o1.giorno, o1.ora,
                  o2.docente_id as doc2_id, d2.cognome||' '||d2.nome as doc2_nome,
                  m1.nome as mat1, m2.nome as mat2
           FROM compresenze cp
           JOIN orario o1 ON o1.id=cp.orario_id_1
           JOIN orario o2 ON o2.id=cp.orario_id_2
           JOIN docenti d1 ON d1.id=o1.docente_id
           JOIN docenti d2 ON d2.id=o2.docente_id
           JOIN classi cl ON cl.id=o1.classe_id
           LEFT JOIN materie m1 ON m1.id=o1.materia_id
           LEFT JOIN materie m2 ON m2.id=o2.materia_id
           ORDER BY o1.giorno, o1.ora"""
    ).fetchall()
    return rows_to_list(rows)


@router.post("/compresenze", status_code=201)
def crea_compresenza(body: CompresenzaCreate, conn: sqlite3.Connection = Depends(get_db)):
    """Collega due slot orario come compresenza."""
    # Verifica che i due slot siano nella stessa classe/giorno/ora
    check = conn.execute(
        """SELECT o1.classe_id=o2.classe_id AND o1.giorno=o2.giorno AND o1.ora=o2.ora as ok
           FROM orario o1, orario o2
           WHERE o1.id=? AND o2.id=?""",
        (body.orario_id_1, body.orario_id_2)
    ).fetchone()
    if not check or not check[0]:
        raise HTTPException(400, "I due slot devono essere nella stessa classe, giorno e ora")

    # Aggiorna tipo a 'compresenza'
    conn.execute(
        "UPDATE orario SET tipo='compresenza' WHERE id IN (?,?)",
        (body.orario_id_1, body.orario_id_2)
    )
    cur = conn.execute(
        "INSERT OR IGNORE INTO compresenze (orario_id_1,orario_id_2,note) VALUES (?,?,?)",
        (body.orario_id_1, body.orario_id_2, body.note)
    )
    return {"id": cur.lastrowid, "message": "Compresenza registrata"}


@router.delete("/compresenze/{comp_id}")
def elimina_compresenza(comp_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute(
        "SELECT orario_id_1, orario_id_2 FROM compresenze WHERE id=?", (comp_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Compresenza non trovata")
    conn.execute(
        "UPDATE orario SET tipo='normale' WHERE id IN (?,?)",
        (row[0], row[1])
    )
    conn.execute("DELETE FROM compresenze WHERE id=?", (comp_id,))
    return {"message": "Compresenza eliminata"}
