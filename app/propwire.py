"""Propwire: build filtered search URLs + import CSV/JSON exports."""
from __future__ import annotations
import csv
import json
from io import StringIO
from urllib.parse import quote
from .targeting import COUNTY_CITIES, FILTERS, is_target, tdu_for, zone

SFR = ["SFR", "Single Family", "Single-Family", "Residential"]

COLMAP = {
    "owner_name": ["owner_name", "owner", "ownername", "owner_1_name", "name"],
    "email": ["email", "email1", "email_1", "owner_email", "emails", "email_address", "skip_trace_email"],
    "phone": ["phone", "phone1", "mobile", "owner_phone", "cell", "skip_trace_phone", "phone_number"],
    "address": ["address", "property_address", "situs_address", "street"],
    "city": ["city", "situs_city", "property_city"],
    "state": ["state", "situs_state"],
    "zip": ["zip", "zipcode", "situs_zip", "postal_code"],
    "county": ["county", "situs_county"],
    "property_type": ["property_type", "propertytype", "type", "prop_type"],
    "sqft": ["sqft", "living_area", "livingareasf", "building_sqft", "sq_ft", "living_sqft"],
    "year_built": ["year_built", "yearbuilt", "year"],
    "owner_occupied": ["owner_occupied", "owneroccupied", "owner_occ"],
}


def _pick(row: dict, field: str):
    keys = {k.lower().strip().replace(" ", "_"): k for k in row}
    for alias in COLMAP[field]:
        if alias in keys:
            return row[keys[alias]]
    return ""


def _bool(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "owner occupied", "owner-occupied"}


def _num(v):
    try:
        return int(str(v).replace(",", "").split(".")[0])
    except Exception:
        return 0


def parse_export(text: str) -> list[dict]:
    text = text.lstrip("\ufeff").strip()
    if text.startswith("["):
        raw = json.loads(text)
        rows = raw if isinstance(raw, list) else []
    else:
        rows = list(csv.DictReader(StringIO(text)))
    out = []
    for r in rows:
        r = {str(k): v for k, v in r.items()}
        em = str(_pick(r, "email") or "").strip()
        if "@example." in em.lower() or "@test.com" in em.lower():
            em = ""
        item = {
            "owner_name": str(_pick(r, "owner_name") or "").strip(),
            "email": em,
            "phone": str(_pick(r, "phone") or "").strip(),
            "address": str(_pick(r, "address") or "").strip(),
            "city": str(_pick(r, "city") or "").strip(),
            "state": (str(_pick(r, "state") or "TX")).strip() or "TX",
            "zip": str(_pick(r, "zip") or "").strip()[:10],
            "county": str(_pick(r, "county") or "").replace(" County", "").strip(),
            "property_type": str(_pick(r, "property_type") or "SFR").strip(),
            "sqft": _num(_pick(r, "sqft")),
            "year_built": _num(_pick(r, "year_built")),
            "owner_occupied": _bool(_pick(r, "owner_occupied")) if _pick(r, "owner_occupied") != "" else True,
            "source": "propwire",
        }
        if item["address"]:
            out.append(item)
    return out


def search_url(city: str, state="TX") -> str:
    filters = {
        "locations": [{"searchType": "C", "city": city, "state": state, "title": f"{city}, {state}"}],
        "homeType": {"values": ["SINGLE_FAMILY"]},
        "livingSquareFeet": {"min": FILTERS["min_sqft"]},
        "yearBuilt": {"min": FILTERS["min_year"]},
        "ownerOccupied": True,
        "mlsActive": False,
    }
    return "https://propwire.com/search?filters=" + quote(json.dumps(filters, separators=(",", ":")))


def search_plan(counties: list[str] | None = None) -> list[dict]:
    plan = []
    for county, cities in COUNTY_CITIES.items():
        if counties and county not in counties:
            continue
        if not is_target(county):
            continue
        for city in cities:
            plan.append({
                "county": county,
                "city": city,
                "zone": zone(county),
                "tdu": tdu_for(county),
                "url": search_url(city),
            })
    return plan
