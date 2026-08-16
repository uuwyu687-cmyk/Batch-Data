import os
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from . import db, targeting, propwire, pipeline, mail, google_api, scanner

load_dotenv()
app = FastAPI(title="Solrite VPP Lead Engine")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/stats")
def stats():
    return db.stats()


@app.get("/api/targeting")
def targeting_data(ec: bool = True, eligible: bool = True):
    rows = targeting.target_counties(ec, eligible)
    return {
        "counties": rows,
        "filters": targeting.FILTERS,
        "allowed_tdu": sorted(targeting.ALLOWED_TDU),
        "propwire": propwire.search_plan([r["county"] for r in rows if r["eligible"]]),
    }


@app.get("/api/leads")
def leads(qualified: int | None = None, status: str | None = None, email: int | None = None):
    q = None if qualified is None else bool(qualified)
    return db.list_leads(status=status, qualified=q, has_email=bool(email))


@app.post("/api/import")
async def import_csv(file: UploadFile = File(...), enrich: bool = True, limit: int = 80):
    text = (await file.read()).decode("utf-8", errors="replace")
    rows = propwire.parse_export(text)
    return pipeline.ingest(rows, do_enrich=enrich, limit=limit)


@app.post("/api/enrich/{lead_id}")
def enrich_one(lead_id: int):
    rows = [l for l in db.list_leads(limit=2000) if l["id"] == lead_id]
    if not rows:
        return {"error": "not found"}
    return pipeline.ingest(rows, do_enrich=True, limit=1)


@app.post("/api/status/{lead_id}")
def status(lead_id: int, value: str = Query(...)):
    db.set_status(lead_id, value)
    return {"ok": True}


@app.get("/api/preview/{lead_id}")
def preview(lead_id: int):
    rows = [l for l in db.list_leads(limit=2000) if l["id"] == lead_id]
    if not rows:
        return {"error": "not found"}
    s, b = mail.render(rows[0])
    return {"subject": s, "body": b}


@app.post("/api/campaign")
def campaign(limit: int = 30):
    return mail.send_campaign(limit=limit)


@app.post("/api/scan")
def scan(city: str = Query("Pearland"), limit: int = 8):
    try:
        return scanner.scan_city(city, limit=max(1, min(limit, 15)))
    except Exception as e:
        return {"error": str(e), "count": 0, "qualified": 0, "leads": []}


@app.get("/api/places")
def places(q: str):
    return google_api.places_city(q)


@app.get("/api/health")
def health():
    return {"ok": True, "google_key": bool(os.getenv("GOOGLE_API_KEY"))}
