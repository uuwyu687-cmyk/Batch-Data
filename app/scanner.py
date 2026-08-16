"""Live homes from OpenStreetMap (public) + Google Solar. Not Propwire."""
import httpx
from . import google_api, pipeline, targeting

OVERPASS = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "HeliosDesk/1.0 (solar lead research)"}


def osm_houses(city: str, limit: int = 12) -> list[dict]:
    geo = google_api.geocode(f"{city}, Texas")
    if not geo:
        return []
    lat, lng = geo["lat"], geo["lng"]
    rows, seen = [], set()
    for d in (0.03, 0.055):
        q = f"""[out:json][timeout:40];
(
  way["building"="house"]["addr:housenumber"]({lat-d},{lng-d},{lat+d},{lng+d});
  way["building"="detached"]["addr:housenumber"]({lat-d},{lng-d},{lat+d},{lng+d});
  way["building"="residential"]["addr:housenumber"]({lat-d},{lng-d},{lat+d},{lng+d});
);
out center {max(limit*6, 50)};"""
        r = httpx.post(OVERPASS, data={"data": q}, headers=HEADERS, timeout=50)
        r.raise_for_status()
        for el in r.json().get("elements") or []:
            tags = el.get("tags") or {}
            c = el.get("center") or {}
            num, street = tags.get("addr:housenumber"), tags.get("addr:street")
            if not (num and street and c.get("lat")):
                continue
            addr = f"{num} {street}"
            if addr in seen:
                continue
            seen.add(addr)
            rows.append({
                "address": addr,
                "city": tags.get("addr:city") or geo.get("city") or city,
                "state": "TX",
                "zip": tags.get("addr:postcode") or "",
                "lat": c["lat"],
                "lng": c["lon"],
                "year_built": 0,
                "property_type": "SFR",
                "owner_occupied": True,
                "source": "live",
            })
            if len(rows) >= limit:
                return rows
    return rows


def scan_city(city: str, limit: int = 8) -> dict:
    geo = google_api.geocode(f"{city}, Texas")
    if not geo:
        return {"error": "city not found", "count": 0, "qualified": 0, "leads": []}
    if geo.get("county") and not targeting.is_target(geo["county"]):
        return {"error": f"{geo.get('county')} County is outside teal/purple eligible TDU", "count": 0, "qualified": 0, "leads": []}
    houses = osm_houses(city, limit=limit)
    enriched = []
    for h in houses:
        solar = google_api.solar_insights(h["lat"], h["lng"])
        if solar.get("ok"):
            h["kw_potential"] = solar["kw_potential"]
            h["roof_suitable"] = solar["roof_suitable"]
            h["existing_solar"] = solar["existing_solar"]
            h["bill_estimate"] = solar.get("bill_estimate")
            h["sqft"] = solar.get("sqft") or h.get("sqft") or 0
            if solar.get("address"):
                h["address"] = solar["address"]
            if solar.get("city"):
                h["city"] = solar["city"]
            if solar.get("zip"):
                h["zip"] = solar["zip"]
        rev = google_api.reverse_geocode(h["lat"], h["lng"])
        if rev:
            h["county"] = rev.get("county") or h.get("county")
            h["zip"] = h.get("zip") or rev.get("zip")
            h["city"] = h.get("city") or rev.get("city")
            if not solar.get("address") and rev.get("address"):
                h["address"] = rev["address"]
        h["owner_name"] = f"Resident · {h.get('address') or city}"
        enriched.append(h)
    return pipeline.ingest(enriched, do_enrich=False, limit=limit)
