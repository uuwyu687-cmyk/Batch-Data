"""Texas VPP targeting: teal Energy Communities + purple eligible markets."""

# IRS Notice 2026-39 — Solrite teal (2026 Energy Community)
EC_2026 = [
    "Angelina","Aransas","Austin","Bee","Bowie","Brazoria","Brooks","Calhoun","Chambers","Colorado",
    "DeWitt","Dimmit","Duval","Edwards","El Paso","Fort Bend","Frio","Galveston","Gonzales","Gregg",
    "Hardin","Harris","Harrison","Hidalgo","Houston","Hudspeth","Jackson","Jasper","Jefferson","Jim Hogg",
    "Jim Wells","Karnes","Kenedy","Kinney","Kleberg","La Salle","Lavaca","Liberty","Live Oak","McMullen",
    "Matagorda","Maverick","Montgomery","Nacogdoches","Newton","Nueces","Orange","Panola","Polk","Real",
    "Refugio","Rusk","Sabine","San Augustine","San Jacinto","San Patricio","Shelby","Starr","Trinity","Tyler",
    "Upshur","Uvalde","Val Verde","Waller","Webb","Wharton","Willacy","Zapata","Zavala",
]

# Solrite purple — eligible market, not an Energy Community
ELIGIBLE_MARKET = [
    "Dallas","Tarrant","Collin","Denton","Rockwall","Kaufman","Ellis","Johnson","Parker","Wise","Hunt","Grayson",
    "McLennan","Bell","Coryell","Wichita",
]

# Not competitive-choice / not Oncor-AEP-CenterPoint-TNMP
REGULATED = {"El Paso", "Hudspeth"}  # El Paso Electric
ENTERGY = {"Jefferson", "Orange"}    # Entergy Texas — not Solrite TDU

# County → primary TDU (best-effort; ZIP-level can still differ)
TDU = {
    "Harris": "CenterPoint", "Fort Bend": "CenterPoint", "Galveston": "CenterPoint",
    "Montgomery": "CenterPoint", "Brazoria": "CenterPoint", "Chambers": "CenterPoint",
    "Liberty": "CenterPoint", "Waller": "CenterPoint", "Wharton": "CenterPoint",
    "Austin": "CenterPoint", "Colorado": "CenterPoint", "Matagorda": "CenterPoint",
    "San Jacinto": "CenterPoint", "Walker": "CenterPoint",
    "Dallas": "Oncor", "Tarrant": "Oncor", "Collin": "Oncor", "Denton": "Oncor",
    "Rockwall": "Oncor", "Kaufman": "Oncor", "Ellis": "Oncor", "Johnson": "Oncor",
    "Parker": "Oncor", "Wise": "Oncor", "Hunt": "Oncor", "Grayson": "Oncor",
    "McLennan": "Oncor", "Bell": "Oncor", "Coryell": "Oncor", "Wichita": "Oncor",
    "Gregg": "Oncor", "Harrison": "Oncor", "Upshur": "Oncor", "Rusk": "Oncor",
    "Panola": "Oncor", "Nacogdoches": "Oncor", "Angelina": "Oncor", "Cherokee": "Oncor",
    "Henderson": "Oncor", "Van Zandt": "Oncor", "Smith": "Oncor", "Bowie": "Oncor",
    "Hidalgo": "AEP", "Cameron": "AEP", "Nueces": "AEP", "San Patricio": "AEP",
    "Webb": "AEP", "Starr": "AEP", "Willacy": "AEP", "Jim Wells": "AEP",
    "Kleberg": "AEP", "Kenedy": "AEP", "Brooks": "AEP", "Duval": "AEP",
    "Jim Hogg": "AEP", "Zapata": "AEP", "Aransas": "AEP", "Refugio": "AEP",
    "Calhoun": "AEP", "Bee": "AEP", "Live Oak": "AEP", "Karnes": "AEP",
    "Goliad": "AEP", "Victoria": "AEP", "Jackson": "AEP", "Lavaca": "AEP",
    "DeWitt": "AEP", "Gonzales": "AEP", "Frio": "AEP", "La Salle": "AEP",
    "McMullen": "AEP", "Dimmit": "AEP", "Maverick": "AEP", "Zavala": "AEP",
    "Uvalde": "AEP", "Val Verde": "AEP", "Kinney": "AEP", "Edwards": "AEP",
    "Real": "AEP",
    "Hardin": "TNMP", "Tyler": "TNMP", "Polk": "TNMP", "Jasper": "TNMP",
    "Newton": "TNMP", "Sabine": "TNMP", "San Augustine": "TNMP", "Shelby": "TNMP",
    "Trinity": "TNMP", "Houston": "TNMP", "Angelina": "Oncor",
}

ALLOWED_TDU = {"Oncor", "AEP", "CenterPoint", "TNMP"}

FILTERS = {
    "owner_occupied": True,
    "property_types": {"sfr", "single family", "single-family", "single family residential", "residential"},
    "min_sqft": 2000,
    "min_year": 1995,
    "min_kw": 10,
    "max_kw": 26,
    "require_roof": True,
    "require_bill": True,
    "require_contact": True,
    "no_existing_solar": True,
}

# High-volume cities used to build Propwire search links
COUNTY_CITIES = {
    "Harris": ["Houston", "Pasadena", "Baytown", "Spring", "Cypress", "Humble", "Katy"],
    "Fort Bend": ["Sugar Land", "Missouri City", "Rosenberg", "Richmond", "Katy"],
    "Montgomery": ["The Woodlands", "Conroe", "Spring", "Magnolia"],
    "Brazoria": ["Pearland", "Alvin", "Lake Jackson", "Angleton"],
    "Galveston": ["League City", "Galveston", "Texas City", "Friendswood"],
    "Dallas": ["Dallas", "Garland", "Irving", "Mesquite", "Grand Prairie"],
    "Tarrant": ["Fort Worth", "Arlington", "Grand Prairie", "Mansfield"],
    "Collin": ["Plano", "Frisco", "McKinney", "Allen", "Richardson"],
    "Denton": ["Denton", "Frisco", "Lewisville", "Flower Mound"],
    "Hidalgo": ["McAllen", "Edinburg", "Mission", "Pharr"],
    "Nueces": ["Corpus Christi"],
    "Webb": ["Laredo"],
    "McLennan": ["Waco"],
    "Bell": ["Killeen", "Temple", "Belton"],
    "Wichita": ["Wichita Falls"],
    "Gregg": ["Longview"],
    "Jefferson": ["Beaumont", "Port Arthur"],
}


import re

def key(name: str) -> str:
    s = re.sub(r"\s+county$", "", (name or "").strip(), flags=re.I)
    return s.upper()


_EC = {key(c) for c in EC_2026}
_EL = {key(c) for c in ELIGIBLE_MARKET}
_REG = {key(c) for c in REGULATED}
_ENT = {key(c) for c in ENTERGY}
_TDU = {key(k): v for k, v in TDU.items()}
_CITIES = {key(k): v for k, v in COUNTY_CITIES.items()}
_LABEL = {key(c): c for c in EC_2026 + ELIGIBLE_MARKET}


def norm(name: str) -> str:
    k = key(name)
    return _LABEL.get(k, (name or "").replace(" County", "").strip())


def zone(county: str) -> str:
    k = key(county)
    if k in _EC:
        return "energy_community"
    if k in _EL:
        return "eligible_market"
    return "out"


def tdu_for(county: str) -> str | None:
    k = key(county)
    if k in _REG or k in _ENT:
        return None
    t = _TDU.get(k)
    return t if t in ALLOWED_TDU else None


def is_target(county: str) -> bool:
    return zone(county) in {"energy_community", "eligible_market"} and tdu_for(county) is not None


def target_counties(include_ec=True, include_eligible=True) -> list[dict]:
    rows = []
    seen = set()
    for src, z in ((EC_2026, "energy_community"), (ELIGIBLE_MARKET, "eligible_market")):
        if z == "energy_community" and not include_ec:
            continue
        if z == "eligible_market" and not include_eligible:
            continue
        for c in src:
            if c in seen:
                continue
            seen.add(c)
            t = tdu_for(c)
            rows.append({
                "county": c,
                "zone": z,
                "tdu": t,
                "eligible": t is not None,
                "cities": _CITIES.get(key(c), []),
            })
    return rows
