# Supplentia v2.0
## Gestionale Sostituzioni Docenti – ITTS E. Scalfaro Catanzaro

### Avvio rapido
```bash
bash start.sh
```
Il server parte su http://localhost:8080

### Reset database
```bash
bash start.sh --reset
```

### Struttura
```
supplentia/
├── config.json           ← configurazione (nome scuola, orario, criteri...)
├── start.sh              ← script di avvio
├── data/
│   └── supplentia.db   ← database SQLite (generato automaticamente)
├── scripts/
│   ├── init_db.py        ← inizializza schema + dati demo
│   └── server.py         ← server HTTP stdlib Python (no pip)
├── backend/
│   └── engine/
│       └── motore.py     ← motore decisionale (7 criteri)
└── frontend/
    ├── index.html        ← SPA shell
    ├── css/main.css      ← design system dark
    └── js/               ← moduli JS per ogni view
```

### Criteri di sostituzione (in ordine di priorità)
| # | ID | Nome | Note |
|---|-----|------|------|
| P0 | `compresenza` | **Compresenza da orario** | Fisso, non spostabile |
| P1 | `ore_disp` | Ore a disposizione | Organico autonomia/potenziamento |
| P2 | `rec_permessi` | Recupero permessi brevi | Docenti con permessi da recuperare |
| P3 | `stessa_classe` | Stessa classe/plesso | Docenti già presenti |
| P4 | `sostegno` | Docenti sostegno | Condizionato ad alunno H |
| P5 | `ore_eccedenti` | Ore eccedenti | Disponibilità volontaria |

### API REST principali
- `GET /api/sostituzioni?data=YYYY-MM-DD`
- `POST /api/engine/run` → `{"data":"YYYY-MM-DD"}`
- `GET /api/compresenze`
- `GET /api/config` / `POST /api/config`
- `PUT /api/criteri` → salva array ordinato criteri
- `POST /api/criteri` → aggiunge criterio custom
- `DELETE /api/criteri/{id}` → rimuove criterio custom

### Requisiti
- Python 3.8+
- Nessuna dipendenza pip

## Importazione Orario da PDF

### Importa orario docenti (tabella riepilogativa + orario completo)
```bash
python3 scripts/importa_orario.py \
  --sostegno Orario_sostegno.pdf \
  --docenti orario_DOCENTI.pdf
```

**Cosa importa:**
- `--sostegno` (obbligatorio): PDF con tabella riepilogativa (Docente, Classe, ore per giorno). Formato: riga per docente con ore di presenza per ogni giorno della settimana (es. `1-2-3-4` = ore 1ª,2ª,3ª,4ª presenti). Inserisce tutti gli slot in `orario_docenti` con tipo `lezione-pdf`.
- `--docenti` (opzionale): PDF orario completo per estrarre le compresenze (riconosce il pattern `DOCENTE1, DOCENTE2 - Classe`).

**Formati PDF supportati:**
- Tabella generata da registri scolastici (Argo, Axios, Excel esportato)
- Il PDF deve avere testo selezionabile (non scansione)
- Richiede `poppler-utils` installato (`sudo apt install poppler-utils`)

**Dopo l'importazione:**
- I docenti vengono creati automaticamente se non esistono già nel DB
- Le classi vengono create automaticamente
- Gli slot vengono deduplicati (no duplicati)
- Le ore `LIBERA/LIBERO` non vengono inserite (usate come ore a disposizione dal motore)

## Importazione orario da PDF classi (metodo raccomandato)

Il PDF **timbro_CLASSI** (orario per classe, una pagina per classe) è il formato più completo:
estrae automaticamente **tutti i docenti**, le loro ore per ogni classe, e le **compresenze**.

```bash
pip install pdfplumber   # solo la prima volta
python3 scripts/importa_orario.py --classi timbro_CLASSI_dal_09_12_25.pdf
```

**Risultato tipico:**
- 136 docenti creati automaticamente
- 1805 slot orario inseriti (classe × giorno × ora × docente)
- 205 compresenze P0 rilevate e inserite

**Formato riconosciuto:** PDF generato dal software di orario scolastico (es. Orario Facile/Argo),
una pagina per classe, layout tabellare con 6 colonne giorni × 6 righe ore.
