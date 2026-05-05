"""SubstManager · API Reportistica"""

from fastapi import APIRouter, Depends
from typing import Optional
import sqlite3
from db.database import get_db

router = APIRouter()


@router.get("/carico-docenti")
def carico_docenti(
    da: Optional[str] = None,
    a: Optional[str] = None,
    conn: sqlite3.Connection = Depends(get_db)
):
    q = """SELECT d.id, d.cognome||' '||d.nome as docente,
                  COUNT(s.id) as tot_sostituzioni,
                  SUM(CASE WHEN cr.codice='ORE_ECCEDENTI' THEN 1 ELSE 0 END) as ore_eccedenti,
                  SUM(CASE WHEN cr.codice='COMPRESENZA'   THEN 1 ELSE 0 END) as compresenze,
                  SUM(CASE WHEN cr.codice='ORE_DISP'      THEN 1 ELSE 0 END) as ore_disp,
                  SUM(CASE WHEN cr.codice='REC_PERMESSI'  THEN 1 ELSE 0 END) as rec_permessi
           FROM docenti d
           LEFT JOIN sostituzioni s ON s.docente_sost_id=d.id AND s.stato='confermata'
           LEFT JOIN criteri cr ON cr.id=s.criterio_id"""
    params = []
    where = []
    if da: where.append("s.data>=?"); params.append(da)
    if a:  where.append("s.data<=?"); params.append(a)
    if where: q += " WHERE " + " AND ".join(where)
    q += " GROUP BY d.id ORDER BY tot_sostituzioni DESC"
    rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


@router.get("/distribuzione-criteri")
def distribuzione_criteri(conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        """SELECT cr.nome, cr.codice, COUNT(s.id) as totale
           FROM criteri cr
           LEFT JOIN sostituzioni s ON s.criterio_id=cr.id AND s.stato='confermata'
           GROUP BY cr.id
           ORDER BY totale DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/trend-mensile")
def trend_mensile(anno: str = "2026", conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        """SELECT strftime('%m', data) as mese,
                  COUNT(*) as totale,
                  SUM(CASE WHEN stato='in_attesa' THEN 1 ELSE 0 END) as non_coperte
           FROM sostituzioni
           WHERE strftime('%Y', data)=?
           GROUP BY mese
           ORDER BY mese""",
        (anno,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/riepilogo-giornaliero/{data}")
def riepilogo_giornaliero(data: str, conn: sqlite3.Connection = Depends(get_db)):
    r = conn.execute(
        """SELECT
               COUNT(DISTINCT a.id) as tot_assenze,
               COUNT(s.id) as tot_sostituzioni,
               SUM(CASE WHEN s.stato='confermata' THEN 1 ELSE 0 END) as coperte,
               SUM(CASE WHEN s.stato='in_attesa'  THEN 1 ELSE 0 END) as in_attesa
           FROM assenze a
           LEFT JOIN sostituzioni s ON s.assenza_id=a.id
           WHERE a.data=?""",
        (data,)
    ).fetchone()
    return dict(r) if r else {}
