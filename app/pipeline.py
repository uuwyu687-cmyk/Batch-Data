import re
from . import db, google_api, melissa, targeting
from .targeting import FILTERS

FAKE_MAIL = ("example.com", "example.org", "test.com", "mailinator.com")


def real_email(v: str) -> str:
    e = (v or "").strip().lower()
    if "@" not in e or "." not in e.split("@")[-1]:
        return ""
    if any(x in e for x in FAKE_MAIL):
        return ""
    return e


def dummy_email(row: dict) -> str:
    raw = row.get("owner_name") or row.get("first_name") or row.get("address") or "homeowner"
    skip = {"resident", "jr", "sr", "ii", "iii", "near", "the", "and"}
    parts = [p for p in re.findall(r"[a-z0-9]+", str(raw).lower()) if p not in skip]
    slug = ".".join(parts[:2]) or "homeowner"
    city = (re.findall(r"[a-z0-9]+", (row.get("city") or "tx").lower()) or ["tx"])[0]
    return f"{slug}.{city}@example.com"


def fill_dummy_email(row: dict) -> dict:
    if real_email(row.get("email") or "") or (row.get("email") or "").strip():
        return row
    row["email"] = dummy_email(row)
    return row


def first_name(name: str) -> str:
    parts = [p for p in (name or "").replace(",", " ").split() if p and p.lower() not in {"jr", "sr", "ii", "iii", "trust", "llc"}]
    return parts[0].title() if parts else "there"


def qualify(row: dict) -> tuple[bool, list[str]]:
    why = []
    county = targeting.norm(row.get("county") or "")
    z = targeting.zone(county)
    tdu = targeting.tdu_for(county)
    if z == "out":
        why.append("not teal/purple")
    if not tdu:
        why.append("TDU not Oncor/AEP/CenterPoint/TNMP")
    if FILTERS["owner_occupied"] and not row.get("owner_occupied"):
        why.append("not owner-occupied")
    pt = (row.get("property_type") or "").lower()
    if pt and not any(x in pt for x in FILTERS["property_types"]) and "sfr" not in pt:
        why.append("not single-family")
    if (row.get("sqft") or 0) < FILTERS["min_sqft"]:
        why.append(f"sqft < {FILTERS['min_sqft']}")
    if (row.get("year_built") or 0) and row["year_built"] < FILTERS["min_year"]:
        why.append(f"built before {FILTERS['min_year']}")
    kw = row.get("kw_potential")
    if kw is not None and (kw < FILTERS["min_kw"] or kw > FILTERS["max_kw"]):
        why.append(f"kW {kw} outside 10–26")
    if FILTERS["require_roof"] and row.get("roof_suitable") is False:
        why.append("roof not suitable")
    if FILTERS["no_existing_solar"] and row.get("existing_solar"):
        why.append("existing solar")
    email = real_email(row.get("email") or "")
    row["email"] = email
    if FILTERS["require_contact"] and not email:
        why.append("no real email")
    if FILTERS["require_bill"] and not row.get("bill_estimate") and not row.get("owner_occupied"):
        why.append("no bill / vacant")
    return (len(why) == 0, why)


def enrich(row: dict) -> dict:
    full = ", ".join(x for x in [row.get("address"), row.get("city"), row.get("state") or "TX", row.get("zip")] if x)
    try:
        geo = google_api.geocode(full) if full else {}
    except Exception:
        geo = {}
    if geo:
        row["lat"] = geo["lat"]
        row["lng"] = geo["lng"]
        if geo.get("county") and not row.get("county"):
            row["county"] = geo["county"]
        if geo.get("zip") and not row.get("zip"):
            row["zip"] = geo["zip"]
        if geo.get("city") and not row.get("city"):
            row["city"] = geo["city"]
        try:
            solar = google_api.solar_insights(geo["lat"], geo["lng"])
        except Exception:
            solar = {}
        if solar.get("ok"):
            row["kw_potential"] = solar["kw_potential"]
            row["roof_suitable"] = solar["roof_suitable"]
            row["existing_solar"] = solar["existing_solar"]
            row["bill_estimate"] = solar.get("bill_estimate") or row.get("bill_estimate")
    if row.get("kw_potential") is None:
        sqft = row.get("sqft") or 0
        row["kw_potential"] = round(sqft * 0.0048, 1)
        row["roof_suitable"] = bool(sqft >= 2000)
        row["bill_estimate"] = row.get("bill_estimate") or round(sqft * 0.055, 0)
    county = targeting.norm(row.get("county") or "")
    row["county"] = county
    row["zone"] = targeting.zone(county)
    row["tdu"] = targeting.tdu_for(county)
    row["energy_community"] = int(row["zone"] == "energy_community")
    row["deregulated"] = int(bool(row["tdu"]))
    try:
        row = melissa.append_contact(row)
    except Exception:
        pass
    row["first_name"] = first_name(row.get("owner_name") or "")
    row["email"] = real_email(row.get("email") or "")
    row["contact_ok"] = int(bool(row["email"]))
    ok, why = qualify(row)
    row["qualified"] = int(ok)
    row["fail_reasons"] = "; ".join(why)
    fill_dummy_email(row)
    row["owner_occupied"] = int(bool(row.get("owner_occupied")))
    row["roof_suitable"] = int(bool(row.get("roof_suitable"))) if row.get("roof_suitable") is not None else None
    row["existing_solar"] = int(bool(row.get("existing_solar")))
    return row


def ingest(rows: list[dict], do_enrich=True, limit=200) -> dict:
    saved = []
    for row in rows[:limit]:
        try:
            if do_enrich:
                row = enrich(row)
            else:
                county = targeting.norm(row.get("county") or "")
                row["county"] = county
                row["zone"] = targeting.zone(county)
                row["tdu"] = targeting.tdu_for(county)
                row["energy_community"] = int(row["zone"] == "energy_community")
                row["deregulated"] = int(bool(row["tdu"]))
                try:
                    row = melissa.append_contact(row)
                except Exception:
                    pass
                row["first_name"] = first_name(row.get("owner_name") or "")
                row["contact_ok"] = int(bool(real_email(row.get("email") or "")))
                row["owner_occupied"] = int(bool(row.get("owner_occupied")))
                if row.get("roof_suitable") is not None:
                    row["roof_suitable"] = int(bool(row["roof_suitable"]))
                row["existing_solar"] = int(bool(row.get("existing_solar")))
                ok, why = qualify(row)
                row["qualified"] = int(ok)
                row["fail_reasons"] = "; ".join(why)
                fill_dummy_email(row)
            row["status"] = row.get("status") or "new"
            lid = db.upsert_lead({k: row.get(k) for k in [
                "owner_name","first_name","email","phone","address","city","state","zip","county",
                "zone","tdu","energy_community","deregulated","owner_occupied","property_type","sqft",
                "year_built","lat","lng","kw_potential","roof_suitable","bill_estimate","existing_solar",
                "contact_ok","qualified","fail_reasons","source","status"
            ] if k in row or k == "status"})
            row["id"] = lid
            saved.append(row)
        except Exception as e:
            row["fail_reasons"] = str(e)
            saved.append(row)
    return {
        "count": len(saved),
        "qualified": sum(1 for r in saved if r.get("qualified")),
        "with_email": sum(1 for r in saved if (r.get("email") or "").strip()),
        "melissa": melissa.status(),
        "leads": saved,
    }
