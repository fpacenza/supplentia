"""
SubstManager · API Criteri di Priorità
Lettura, creazione, modifica, cancellazione e riordino dei criteri.
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Optional
import sqlite3

from db.database import get_db, rows_to_list, row_to_dict

router = APIRouter()


# ── Modelli Pydantic ──────────────────────────────────────────

class CriterioCreate(BaseModel):
    codice: str = Field(..., min_length=2, max_length=30)
    nome: str = Field(..., min_length=2, max_length=100)
    descrizione: Optional[str] = None
    attivo: bool = True
    ordine: int = Field(..., ge=1)
    parametri: dict = {}


class CriterioUpdate(BaseModel):
    nome: Optional[str] = None
    descrizione: Optional[str] = None
    attivo: Optional[bool] = None
    parametri: Optional[dict] = None


class OrdineItem(BaseModel):
    id: int
    ordine: int


# ── ENDPOINT ──────────────────────────────────────────────────

@router.get("/")
def lista_criteri(conn: sqlite3.Connection = Depends(get_db)):
    """Restituisce tutti i criteri ordinati per priorità."""
    rows = conn.execute(
        "SELECT * FROM criteri ORDER BY ordine ASC"
    ).fetchall()
    result = []
    for r in rows:
        c = dict(r)
        c['parametri'] = json.loads(c.get('parametri') or '{}')
        result.append(c)
    return result


@router.get("/{criterio_id}")
def get_criterio(criterio_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM criteri WHERE id=?", (criterio_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Criterio non trovato")
    c = dict(row)
    c['parametri'] = json.loads(c.get('parametri') or '{}')
    return c


@router.post("/", status_code=201)
def crea_criterio(body: CriterioCreate, conn: sqlite3.Connection = Depends(get_db)):
    """Crea un nuovo criterio personalizzato."""
    # Normalizza codice
    codice = body.codice.upper().replace(' ', '_')

    # Verifica unicità codice
    existing = conn.execute(
        "SELECT id FROM criteri WHERE codice=?", (codice,)
    ).fetchone()
    if existing:
        raise HTTPException(400, f"Criterio con codice '{codice}' già esistente")

    # Sposta tutti i criteri con ordine >= body.ordine
    conn.execute(
        "UPDATE criteri SET ordine = ordine + 1 WHERE ordine >= ?", (body.ordine,)
    )

    cur = conn.execute(
        """INSERT INTO criteri (codice, nome, descrizione, attivo, ordine, built_in, parametri)
           VALUES (?, ?, ?, ?, ?, 0, ?)""",
        (codice, body.nome, body.descrizione, int(body.attivo),
         body.ordine, json.dumps(body.parametri))
    )
    return {"id": cur.lastrowid, "message": "Criterio creato con successo"}


@router.put("/{criterio_id}")
def aggiorna_criterio(
    criterio_id: int,
    body: CriterioUpdate,
    conn: sqlite3.Connection = Depends(get_db)
):
    """Aggiorna nome, descrizione, stato o parametri di un criterio."""
    row = conn.execute("SELECT * FROM criteri WHERE id=?", (criterio_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Criterio non trovato")

    c = dict(row)
    updates = []
    values = []

    if body.nome is not None:
        updates.append("nome=?")
        values.append(body.nome)
    if body.descrizione is not None:
        updates.append("descrizione=?")
        values.append(body.descrizione)
    if body.attivo is not None:
        updates.append("attivo=?")
        values.append(int(body.attivo))
    if body.parametri is not None:
        updates.append("parametri=?")
        values.append(json.dumps(body.parametri))

    if not updates:
        return {"message": "Nessuna modifica"}

    values.append(criterio_id)
    conn.execute(f"UPDATE criteri SET {', '.join(updates)} WHERE id=?", values)
    return {"message": "Criterio aggiornato"}


@router.patch("/{criterio_id}/toggle")
def toggle_criterio(criterio_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Attiva/disattiva un criterio."""
    row = conn.execute("SELECT attivo FROM criteri WHERE id=?", (criterio_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Criterio non trovato")
    nuovo = 1 - row[0]
    conn.execute("UPDATE criteri SET attivo=? WHERE id=?", (nuovo, criterio_id))
    return {"attivo": bool(nuovo)}


@router.post("/riordina")
def riordina_criteri(
    ordini: list[OrdineItem] = Body(...),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Aggiorna l'ordine di tutti i criteri.
    Accetta lista [{id: X, ordine: Y}, ...].
    """
    for item in ordini:
        conn.execute(
            "UPDATE criteri SET ordine=? WHERE id=?",
            (item.ordine, item.id)
        )
    return {"message": f"Ordine aggiornato per {len(ordini)} criteri"}


@router.delete("/{criterio_id}")
def elimina_criterio(criterio_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Elimina un criterio personalizzato (non i built-in)."""
    row = conn.execute(
        "SELECT built_in FROM criteri WHERE id=?", (criterio_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Criterio non trovato")
    if row[0]:
        raise HTTPException(400, "I criteri built-in non possono essere eliminati")
    conn.execute("DELETE FROM criteri WHERE id=?", (criterio_id,))
    return {"message": "Criterio eliminato"}


@router.put("/{criterio_id}/parametri")
def aggiorna_parametri(
    criterio_id: int,
    parametri: dict = Body(...),
    conn: sqlite3.Connection = Depends(get_db)
):
    """Aggiorna solo i parametri configurabili di un criterio."""
    row = conn.execute("SELECT id FROM criteri WHERE id=?", (criterio_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Criterio non trovato")
    conn.execute(
        "UPDATE criteri SET parametri=? WHERE id=?",
        (json.dumps(parametri), criterio_id)
    )
    return {"message": "Parametri aggiornati"}
