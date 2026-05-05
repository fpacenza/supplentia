"""
Supplentia · Backend FastAPI
Gestionale Sostituzioni Docenti
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from db.database import init_db
from api import (
    assenze,
    sostituzioni,
    docenti,
    orario,
    criteri,
    reportistica,
    utenti,
    importazione,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inizializzazione al avvio."""
    print("🚀 Supplentia avviato — inizializzazione database...")
    init_db()
    print("✅ Database pronto.")
    yield
    print("👋 Supplentia arrestato.")


app = FastAPI(
    title="Supplentia API",
    description="Gestionale Sostituzioni Docenti",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API ROUTES ────────────────────────────────────────────────
app.include_router(assenze.router,       prefix="/api/assenze",       tags=["Assenze"])
app.include_router(sostituzioni.router,  prefix="/api/sostituzioni",  tags=["Sostituzioni"])
app.include_router(docenti.router,       prefix="/api/docenti",       tags=["Docenti"])
app.include_router(orario.router,        prefix="/api/orario",        tags=["Orario"])
app.include_router(criteri.router,       prefix="/api/criteri",       tags=["Criteri"])
app.include_router(reportistica.router,  prefix="/api/report",        tags=["Reportistica"])
app.include_router(utenti.router,        prefix="/api/utenti",        tags=["Utenti"])
app.include_router(importazione.router,  prefix="/api/importa",       tags=["Importazione"])

# ── FRONTEND STATICO ──────────────────────────────────────────
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_path):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "css")), name="css")
    app.mount("/js",     StaticFiles(directory=os.path.join(frontend_path, "js")),  name="js")

    @app.get("/", include_in_schema=False)
    async def root():
        return FileResponse(os.path.join(frontend_path, "index.html"))

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        """SPA fallback — tutte le route non-API tornano index.html."""
        fp = os.path.join(frontend_path, path)
        if os.path.isfile(fp):
            return FileResponse(fp)
        return FileResponse(os.path.join(frontend_path, "index.html"))


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
