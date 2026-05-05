#!/usr/bin/env python3
"""
SubstManager v2 - Inizializzazione Database
Crea il database SQLite con schema completo e dati demo.
"""

import sqlite3
import os
import sys
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'substmanager.db')

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ─────────────────────────── STRUTTURA ───────────────────────────

CREATE TABLE IF NOT EXISTS plessi (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    indirizzo   TEXT,
    telefono    TEXT
);

CREATE TABLE IF NOT EXISTS classi (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,          -- es. "3A"
    anno        INTEGER NOT NULL,       -- 1..5
    sezione     TEXT NOT NULL,          -- A, B, C ...
    plesso_id   INTEGER REFERENCES plessi(id),
    indirizzo   TEXT                    -- es. "Informatica", "Meccanica"
);

CREATE TABLE IF NOT EXISTS docenti (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cognome         TEXT NOT NULL,
    nome            TEXT NOT NULL,
    materia         TEXT,
    ruolo           TEXT NOT NULL DEFAULT 'curriculare',  -- curriculare|sostegno|potenziamento
    plesso_id       INTEGER REFERENCES plessi(id),
    email           TEXT,
    telefono        TEXT,
    ore_cattedra    INTEGER DEFAULT 18,
    disp_ore_eccedenti INTEGER DEFAULT 1,  -- 1=sì, 0=no
    escluso_motore  INTEGER DEFAULT 0,
    note            TEXT
);

CREATE TABLE IF NOT EXISTS alunni_h (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cognome     TEXT NOT NULL,
    nome        TEXT NOT NULL,
    classe_id   INTEGER REFERENCES classi(id),
    docente_sostegno_id INTEGER REFERENCES docenti(id),
    tipo        TEXT DEFAULT 'H'       -- H|BES|DSA
);

-- ─────────────────────────── ORARIO ───────────────────────────

CREATE TABLE IF NOT EXISTS orario_docenti (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    docente_id  INTEGER NOT NULL REFERENCES docenti(id) ON DELETE CASCADE,
    classe_id   INTEGER REFERENCES classi(id),
    giorno      INTEGER NOT NULL,      -- 1=Lun .. 5=Ven
    ora         INTEGER NOT NULL,      -- 1..6
    tipo        TEXT DEFAULT 'lezione', -- lezione|disposizione|potenziamento|sostegno
    materia     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS uscite_didattiche (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    data        TEXT NOT NULL,           -- data dell'uscita (ISO: YYYY-MM-DD)
    classe_id   INTEGER NOT NULL REFERENCES classi(id),
    ore_json    TEXT NOT NULL DEFAULT '[1,2,3,4,5,6]',  -- ore interessate
    note        TEXT DEFAULT '',
);

CREATE TABLE IF NOT EXISTS compresenze (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    classe_id   INTEGER NOT NULL REFERENCES classi(id),
    giorno      INTEGER NOT NULL,
    ora         INTEGER NOT NULL,
    docente1_id INTEGER NOT NULL REFERENCES docenti(id),
    docente2_id INTEGER NOT NULL REFERENCES docenti(id),
    note        TEXT,
    UNIQUE(classe_id, giorno, ora, docente1_id, docente2_id)
);

-- ─────────────────────────── OPERATIVI ───────────────────────────

CREATE TABLE IF NOT EXISTS assenze (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    docente_id  INTEGER NOT NULL REFERENCES docenti(id),
    data        TEXT NOT NULL,         -- ISO date YYYY-MM-DD
    tipo        TEXT NOT NULL,         -- malattia|permesso|ferie|aggiornamento|altro
    ore_json    TEXT NOT NULL,         -- JSON array es. [1,2,3]
    note        TEXT,
);

CREATE TABLE IF NOT EXISTS permessi_recupero (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    docente_id  INTEGER NOT NULL REFERENCES docenti(id),
    ore_da_recuperare INTEGER DEFAULT 0,
    aggiornato  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sostituzioni (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    assenza_id      INTEGER REFERENCES assenze(id),
    data            TEXT NOT NULL,
    docente_assente_id INTEGER NOT NULL REFERENCES docenti(id),
    docente_sostituto_id INTEGER REFERENCES docenti(id),
    classe_id       INTEGER REFERENCES classi(id),
    ora             INTEGER NOT NULL,
    criterio_id     TEXT,
    punteggio       INTEGER DEFAULT 0,
    tipo            TEXT DEFAULT 'auto',  -- auto|manuale
    stato           TEXT DEFAULT 'attesa', -- attesa|confermata|bloccata|annullata
    bloccata        INTEGER DEFAULT 0,
    motivazione     TEXT,
    operatore       TEXT,
    inserita_il     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ore_eccedenti (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    docente_id  INTEGER NOT NULL REFERENCES docenti(id),
    sostituzione_id INTEGER REFERENCES sostituzioni(id) ON DELETE CASCADE,
    data        TEXT NOT NULL,
    settimana   TEXT NOT NULL,         -- es. "2026-W18"
    note        TEXT
);

CREATE TABLE IF NOT EXISTS log_operazioni (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT DEFAULT (datetime('now')),
    tipo        TEXT,
    entita      TEXT,
    entita_id   INTEGER,
    descrizione TEXT,
    operatore   TEXT
);

CREATE TABLE IF NOT EXISTS utenti (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    nome        TEXT NOT NULL,
    ruolo       TEXT DEFAULT 'operatore', -- dirigente|vicepreside|operatore|segreteria
    email       TEXT,
    attivo      INTEGER DEFAULT 1
);

-- ─────────────────────────── INDICI ───────────────────────────

CREATE INDEX IF NOT EXISTS idx_assenze_data ON assenze(data);
CREATE INDEX IF NOT EXISTS idx_assenze_docente ON assenze(docente_id, data);
CREATE INDEX IF NOT EXISTS idx_sostituzioni_data ON sostituzioni(data);
CREATE INDEX IF NOT EXISTS idx_orario ON orario_docenti(docente_id, giorno, ora);
CREATE INDEX IF NOT EXISTS idx_compresenze ON compresenze(classe_id, giorno, ora);
"""

SEED = """
-- ─── PLESSI (struttura base, sempre presenti) ───
INSERT OR IGNORE INTO plessi (id, nome, indirizzo) VALUES
  (1, 'Sede Centrale', 'Lamezia Terme'),
  (2, 'Plesso B',      'Lamezia Terme');

-- ─── UTENTI di sistema ───
INSERT OR IGNORE INTO utenti (id, username, nome, ruolo, email) VALUES
  (1, 'vicepreside', 'Vicepreside',  'vicepreside', ''),
  (2, 'dirigente',   'Dirigente',    'dirigente',   ''),
  (3, 'segreteria',  'Segreteria',   'segreteria',  '');
"""


def init():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    exists = os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)
        conn.executescript(SEED)
        conn.commit()
        action = "aggiornato" if exists else "creato"
        print(f"✓ Database {action}: {DB_PATH}")
        # Verifica conteggi
        print(f"  DB pronto – aggiungi i docenti dalla sezione 'Docenti' dell'applicazione")
    finally:
        conn.close()

if __name__ == '__main__':
    init()
