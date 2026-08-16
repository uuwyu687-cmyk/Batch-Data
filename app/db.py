import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "leads.db"
DB.parent.mkdir(exist_ok=True)

DDL = """
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_name TEXT,
  first_name TEXT,
  email TEXT,
  phone TEXT,
  address TEXT,
  city TEXT,
  state TEXT DEFAULT 'TX',
  zip TEXT,
  county TEXT,
  zone TEXT,
  tdu TEXT,
  energy_community INTEGER,
  deregulated INTEGER,
  owner_occupied INTEGER,
  property_type TEXT,
  sqft INTEGER,
  year_built INTEGER,
  lat REAL,
  lng REAL,
  kw_potential REAL,
  roof_suitable INTEGER,
  bill_estimate REAL,
  existing_solar INTEGER,
  contact_ok INTEGER,
  qualified INTEGER,
  fail_reasons TEXT,
  source TEXT,
  status TEXT DEFAULT 'new',
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER,
  subject TEXT,
  body TEXT,
  status TEXT,
  sent_at TEXT,
  FOREIGN KEY(lead_id) REFERENCES leads(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_addr ON leads(address, zip);
"""


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(DDL)
    return c


def upsert_lead(row: dict) -> int:
    keys = [k for k in row if k != "id"]
    cols = ",".join(keys)
    qs = ",".join("?" * len(keys))
    updates = ",".join(f"{k}=excluded.{k}" for k in keys if k not in ("address", "zip", "created_at"))
    sql = f"INSERT INTO leads ({cols}) VALUES ({qs}) ON CONFLICT(address, zip) DO UPDATE SET {updates}"
    with conn() as c:
        cur = c.execute(sql, [row[k] for k in keys])
        if cur.lastrowid:
            return cur.lastrowid
        r = c.execute("SELECT id FROM leads WHERE address=? AND zip=?", (row.get("address"), row.get("zip"))).fetchone()
        return r["id"] if r else 0


def list_leads(status=None, qualified=None, has_email=None, limit=500):
    q = "SELECT * FROM leads WHERE 1=1"
    args = []
    if status:
        q += " AND status=?"
        args.append(status)
    if qualified is not None:
        q += " AND qualified=?"
        args.append(int(qualified))
    if has_email:
        q += " AND email IS NOT NULL AND email != '' AND email NOT LIKE '%@example.%'"
    q += " ORDER BY qualified DESC, kw_potential DESC, id DESC LIMIT ?"
    args.append(limit)
    with conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def stats():
    with conn() as c:
        n = lambda sql: c.execute(sql).fetchone()[0]
        return {
            "total": n("SELECT COUNT(*) FROM leads"),
            "qualified": n("SELECT COUNT(*) FROM leads WHERE qualified=1"),
            "with_email": n("SELECT COUNT(*) FROM leads WHERE email IS NOT NULL AND email != '' AND email NOT LIKE '%@example.%'"),
            "new": n("SELECT COUNT(*) FROM leads WHERE status='new'"),
            "contacted": n("SELECT COUNT(*) FROM leads WHERE status='contacted'"),
            "interested": n("SELECT COUNT(*) FROM leads WHERE status='interested'"),
            "booked": n("SELECT COUNT(*) FROM leads WHERE status='booked'"),
        }


def set_status(lead_id: int, status: str):
    with conn() as c:
        c.execute("UPDATE leads SET status=? WHERE id=?", (status, lead_id))


def log_message(lead_id, subject, body, status):
    with conn() as c:
        c.execute(
            "INSERT INTO messages (lead_id,subject,body,status,sent_at) VALUES (?,?,?,?,datetime('now'))",
            (lead_id, subject, body, status),
        )
