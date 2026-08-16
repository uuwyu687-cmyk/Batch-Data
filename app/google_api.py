import os
import httpx
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("GOOGLE_API_KEY", "")
GEO = "https://maps.googleapis.com/maps/api/geocode/json"
SOLAR = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
PLACES = "https://maps.googleapis.com/maps/api/place/textsearch/json"


def geocode(address: str) -> dict:
    r = httpx.get(GEO, params={"address": address, "key": KEY}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK" or not data.get("results"):
        return {}
    top = data["results"][0]
    loc = top["geometry"]["location"]
    comps = {c["types"][0]: c["long_name"] for c in top.get("address_components", []) if c.get("types")}
    county = (comps.get("administrative_area_level_2") or "").replace(" County", "")
    return {
        "lat": loc["lat"],
        "lng": loc["lng"],
        "formatted": top.get("formatted_address"),
        "county": county,
        "city": comps.get("locality") or comps.get("sublocality") or "",
        "zip": comps.get("postal_code") or "",
        "place_id": top.get("place_id"),
    }


def reverse_geocode(lat: float, lng: float) -> dict:
    r = httpx.get(GEO, params={"latlng": f"{lat},{lng}", "key": KEY}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK" or not data.get("results"):
        return {}
    top = data["results"][0]
    comps = {c["types"][0]: c["long_name"] for c in top.get("address_components", []) if c.get("types")}
    street = " ".join(x for x in [comps.get("street_number"), comps.get("route")] if x)
    return {
        "address": street or (top.get("formatted_address") or "").split(",")[0],
        "formatted": top.get("formatted_address"),
        "county": (comps.get("administrative_area_level_2") or "").replace(" County", ""),
        "city": comps.get("locality") or comps.get("sublocality") or "",
        "zip": comps.get("postal_code") or "",
    }


def solar_insights(lat: float, lng: float) -> dict:
    r = httpx.get(
        SOLAR,
        params={
            "location.latitude": lat,
            "location.longitude": lng,
            "requiredQuality": "MEDIUM",
            "key": KEY,
        },
        timeout=30,
    )
    if r.status_code != 200:
        return {"ok": False, "error": r.text[:300]}
    d = r.json()
    pot = d.get("solarPotential") or {}
    watts = float(pot.get("panelCapacityWatts") or 400)
    panels = int(pot.get("maxArrayPanelsCount") or 0)
    kw_max = round(panels * watts / 1000, 2)
    residential = 10 <= kw_max <= 40
    kw = min(kw_max, 26.0) if kw_max >= 10 else kw_max
    sun = float(pot.get("maxSunshineHoursPerYear") or 0)
    roof_m2 = float((pot.get("wholeRoofStats") or {}).get("areaMeters2") or 0)
    # Existing panels: if imagery notes / roof already covered. Solar API has no hard flag;
    # treat very low usable fraction on a large roof as a review item, not auto-fail.
    existing = False
    cfgs = pot.get("solarPanelConfigs") or []
    yearly = 0
    for cfg in cfgs:
        p = int(cfg.get("panelsCount") or 0)
        if 10 <= p * watts / 1000 <= 26:
            yearly = float(cfg.get("yearlyEnergyDcKwh") or 0)
            break
    if not yearly and cfgs:
        yearly = float(cfgs[-1].get("yearlyEnergyDcKwh") or 0)
    roof_ok = sun >= 1400 and kw_max >= 10 and roof_m2 >= 40 and residential
    bill = round(yearly * 0.14 / 12, 2) if yearly else None
    postal = d.get("postalAddress") or {}
    line = (postal.get("addressLines") or [None])[0]
    return {
        "ok": True,
        "kw_potential": round(kw, 2),
        "kw_max": kw_max,
        "panels": panels,
        "sun_hours": sun,
        "roof_m2": round(roof_m2, 1),
        "roof_suitable": roof_ok,
        "existing_solar": existing,
        "yearly_kwh": round(yearly, 0),
        "bill_estimate": bill,
        "sqft": int(roof_m2 * 10.764) if roof_m2 else 0,
        "address": line or "",
        "city": postal.get("locality") or "",
        "zip": postal.get("postalCode") or "",
        "state": postal.get("administrativeArea") or "TX",
    }


def places_city(query: str) -> list[dict]:
    r = httpx.get(PLACES, params={"query": query, "key": KEY, "region": "us"}, timeout=20)
    r.raise_for_status()
    out = []
    for p in (r.json().get("results") or [])[:8]:
        loc = (p.get("geometry") or {}).get("location") or {}
        out.append({"name": p.get("name"), "address": p.get("formatted_address"), "lat": loc.get("lat"), "lng": loc.get("lng")})
    return out
