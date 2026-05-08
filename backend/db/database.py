"""
SubstManager · Database Layer
Gestione connessione SQLite e inizializzazione schema
"""

import sqlite3
import os
from pathlib import Path
from typing import Generator

# ── PERCORSI ──────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent.parent
DATA_DIR   = BASE_DIR / "data"
DB_PATH    = DATA_DIR / "substmanager.db"
SCHEMA_SQL = DATA_DIR / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """Apre una connessione SQLite con row_factory e FK attive."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_db() -> Generator:
    """Dependency FastAPI: connessione per-request con auto-close."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Crea il database e applica schema.sql se non esiste già."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not SCHEMA_SQL.exists():
        print(f"⚠️  schema.sql non trovato in {SCHEMA_SQL}")
        return

    conn = get_connection()
    try:
        # Controlla se il db è già inizializzato
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='criteri'"
        )
        if cur.fetchone() is None:
            print("📦 Applicazione schema e dati iniziali...")
            sql = SCHEMA_SQL.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.commit()
            print("✅ Schema applicato con successo.")
        else:
            print("✅ Database già inizializzato.")
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    """Converte sqlite3.Row in dict."""
    return dict(row) if row else None


def rows_to_list(rows) -> list:
    """Converte lista di sqlite3.Row in lista di dict."""
    return [dict(r) for r in rows]
