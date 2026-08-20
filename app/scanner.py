"""Live homes from OpenStreetMap (public) + Google Solar. Not Propwire."""
import os
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
    try:
        d = 0.04
        q = f"""[out:json][timeout:20];
(
  way["building"="house"]["addr:housenumber"]({lat-d},{lng-d},{lat+d},{lng+d});
  way["building"="detached"]["addr:housenumber"]({lat-d},{lng-d},{lat+d},{lng+d});
);
out center {max(limit*5, 25)};"""
        r = httpx.post(OVERPASS, data={"data": q}, headers=HEADERS, timeout=22)
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
                break
    except Exception:
        pass
    if rows:
        return rows[:limit]
    # Fallback: sample nearby points if OSM is slow/down
    for i, (dy, dx) in enumerate(((0.008, 0.008), (0.01, -0.006), (-0.007, 0.01), (0.012, 0.004))):
        if i >= limit:
            break
        rows.append({
            "address": f"Near {city}",
            "city": geo.get("city") or city,
            "state": "TX",
            "zip": geo.get("zip") or "",
            "lat": lat + dy,
            "lng": lng + dx,
            "year_built": 0,
            "property_type": "SFR",
            "owner_occupied": True,
            "source": "live",
        })
    return rows[:limit]


def scan_city(city: str, limit: int = 8) -> dict:
    try:
        if os.getenv("VERCEL"):
            limit = min(limit, 3)
        geo = google_api.geocode(f"{city}, Texas")
        if not geo:
            return {"error": "city not found", "count": 0, "qualified": 0, "with_email": 0, "leads": []}
        if geo.get("county") and not targeting.is_target(geo["county"]):
            return {"error": f"{geo.get('county')} County is outside teal/purple eligible TDU", "count": 0, "qualified": 0, "with_email": 0, "leads": []}
        houses = osm_houses(city, limit=limit)
        if not houses:
            return {"error": "No houses found in this city right now. Try another Texas city.", "count": 0, "qualified": 0, "with_email": 0, "leads": []}
        enriched = []
        for h in houses:
            try:
                solar = google_api.solar_insights(h["lat"], h["lng"])
            except Exception:
                solar = {}
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
            h["county"] = h.get("county") or geo.get("county") or ""
            if not h.get("county") and not os.getenv("VERCEL"):
                try:
                    rev = google_api.reverse_geocode(h["lat"], h["lng"])
                except Exception:
                    rev = {}
                if rev:
                    h["county"] = rev.get("county") or h.get("county")
                    h["zip"] = h.get("zip") or rev.get("zip")
                    h["city"] = h.get("city") or rev.get("city")
                    if not h.get("address") or h["address"].startswith("Near "):
                        if rev.get("address"):
                            h["address"] = rev["address"]
            h["county"] = h.get("county") or geo.get("county") or ""
            h["owner_name"] = f"Resident · {h.get('address') or city}"
            enriched.append(h)
        return pipeline.ingest(enriched, do_enrich=False, limit=limit)
    except Exception as e:
        return {"error": str(e), "count": 0, "qualified": 0, "with_email": 0, "leads": []}

