"""Supplentia · API Utenti"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import sqlite3
from db.database import get_db, rows_to_list

router = APIRouter()


class UtenteCreate(BaseModel):
    username: str
    password: str
    nome: str
    ruolo: str  # dirigente|vicepreside|segreteria|readonly


@router.get("/")
def lista_utenti(conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT id, username, nome, ruolo, attivo FROM utenti ORDER BY nome"
    ).fetchall()
    return rows_to_list(rows)


@router.post("/", status_code=201)
def crea_utente(body: UtenteCreate, conn: sqlite3.Connection = Depends(get_db)):
    import bcrypt
    pw_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    try:
        cur = conn.execute(
            "INSERT INTO utenti (username,password_hash,nome,ruolo) VALUES (?,?,?,?)",
            (body.username, pw_hash, body.nome, body.ruolo)
        )
        return {"id": cur.lastrowid}
    except Exception:
        raise HTTPException(400, "Username già esistente")
