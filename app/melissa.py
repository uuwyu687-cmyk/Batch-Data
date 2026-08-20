"""Melissa: Property lookup + Personator Consumer (portal-compatible GET)."""
from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

from . import db

load_dotenv()

CONSUMER = "https://personator.melissadata.net/v3/WEB/ContactVerify/doContactVerify"
PROPERTY = "https://property.melissadata.net/v4/WEB/LookupProperty"

_mem: dict[str, dict] = {}
_auth_failed = False
_append_blocked = False
_last_code = ""
_working_credits = ""
_AUTH_FAIL = ("GE04", "GE05", "GE06", "GE09", "GE10", "GE11")


def _note(codes: str) -> None:
    global _last_code
    c = str(codes or "").strip()
    if c:
        _last_code = c


def _is_auth_fail(codes: str) -> bool:
    _note(codes)
    return any(x in str(codes or "") for x in _AUTH_FAIL)


def status() -> dict:
    return {
        "configured": configured(),
        "auth_ok": configured() and not _auth_failed,
        "last_code": _last_code,
        "append_blocked": _append_blocked,
    }


def _clean_key(raw: str) -> str:
    return (raw or "").strip().strip('"').strip("'")


def license_key() -> str:
    return _clean_key(os.getenv("MELISSA_LICENSE_KEY") or "")


def credits_key() -> str:
    return _clean_key(os.getenv("MELISSA_CREDITS_KEY") or "")


def configured() -> bool:
    return bool(license_key() or credits_key())


def _key_variants() -> list[str]:
    """Portal shows **; chat/copy sometimes pastes a single *. Try both."""
    seen: list[str] = []
    for raw in (credits_key(), license_key()):
        if not raw:
            continue
        cands = [raw]
        if "*" in raw and "**" not in raw:
            cands.append(raw.replace("*", "**"))
        elif "**" in raw:
            cands.append(raw.replace("**", "*"))
        for k in cands:
            if k not in seen:
                seen.append(k)
    if _working_credits and _working_credits in seen:
        seen.remove(_working_credits)
        seen.insert(0, _working_credits)
    return seen


def _remember_key(key: str) -> None:
    global _working_credits
    if key:
        _working_credits = key


def _cache_key(address: str, city: str, state: str, zipc: str) -> str:
    return "|".join(x.strip().lower() for x in [address, city, state, zipc])


def _is_placeholder_name(name: str) -> bool:
    n = (name or "").strip().lower()
    return (not n) or n.startswith("resident") or n.startswith("near ")


def _real_email(v: str) -> str:
    e = (v or "").strip().lower()
    if "@" not in e or "." not in e.split("@")[-1]:
        return ""
    if any(x in e for x in ("example.com", "example.org", "test.com", "mailinator.com")):
        return ""
    if e.endswith("@melissa.com"):
        return ""
    return e


def _first_str(*vals) -> str:
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _apply(row: dict, hit: dict) -> dict:
    email = _real_email(hit.get("email") or "")
    phone = _first_str(hit.get("phone"))
    name = _first_str(hit.get("owner_name"))
    if email:
        row["email"] = email
    if phone and not (row.get("phone") or "").strip():
        row["phone"] = phone
    if name and _is_placeholder_name(row.get("owner_name") or ""):
        row["owner_name"] = name
    if hit.get("owner_occupied") is not None:
        row["owner_occupied"] = int(bool(hit["owner_occupied"]))
    if hit.get("sqft") and not (row.get("sqft") or 0):
        try:
            row["sqft"] = int(float(hit["sqft"]))
        except (TypeError, ValueError):
            pass
    if hit.get("year_built") and not (row.get("year_built") or 0):
        try:
            row["year_built"] = int(hit["year_built"])
        except (TypeError, ValueError):
            pass
    if hit.get("zip") and not (row.get("zip") or "").strip():
        row["zip"] = hit["zip"]
    return row


def _cache_get(key: str) -> dict | None:
    if key in _mem:
        return _mem[key]
    try:
        with db.conn() as c:
            r = c.execute(
                "SELECT email, phone, owner_name FROM melissa_cache WHERE addr_key=?",
                (key,),
            ).fetchone()
        if not r:
            return None
        hit = {"email": r["email"] or "", "phone": r["phone"] or "", "owner_name": r["owner_name"] or ""}
        _mem[key] = hit
        return hit
    except Exception:
        return None


def _cache_set(key: str, hit: dict) -> None:
    _mem[key] = hit
    try:
        with db.conn() as c:
            c.execute(
                """INSERT INTO melissa_cache (addr_key, email, phone, owner_name, results, source, updated_at)
                   VALUES (?,?,?,?,?,?,datetime('now'))
                   ON CONFLICT(addr_key) DO UPDATE SET
                     email=excluded.email, phone=excluded.phone, owner_name=excluded.owner_name,
                     results=excluded.results, source=excluded.source, updated_at=datetime('now')""",
                (
                    key,
                    hit.get("email") or "",
                    hit.get("phone") or "",
                    hit.get("owner_name") or "",
                    hit.get("results") or "",
                    hit.get("source") or "",
                ),
            )
    except Exception:
        pass


def _get(url: str, params: dict) -> dict:
    r = httpx.get(url, params=params, headers={"Accept": "application/json"}, timeout=22)
    return r.json()


def _personator_get(act: str, address: str, city: str, state: str, zipc: str, opt: str = "") -> dict:
    global _auth_failed, _append_blocked
    last = {}
    for key in _key_variants():
        params: dict[str, Any] = {
            "id": key,
            "act": act,
            "format": "JSON",
            "t": "helios",
            "a1": address,
            "city": city,
            "state": state,
            "postal": zipc,
        }
        if opt:
            params["opt"] = opt
        try:
            data = _get(CONSUMER, params)
        except Exception:
            continue
        codes = str(data.get("TransmissionResults") or "")
        _note(codes)
        if _is_auth_fail(codes):
            last = {"results": codes, "source": "personator"}
            continue
        if "GE29" in codes or "GE21" in codes:
            _append_blocked = True
            _remember_key(key)
            return {"results": codes, "source": "personator"}
        _remember_key(key)
        recs = data.get("Records") or []
        rec = recs[0] if recs else {}
        return {
            "email": _real_email(_first_str(rec.get("EmailAddress"), rec.get("Email"))),
            "phone": _first_str(rec.get("PhoneNumber"), rec.get("Phone")),
            "owner_name": _first_str(
                rec.get("NameFull"),
                rec.get("FullName"),
                f"{rec.get('FirstName', '')} {rec.get('LastName', '')}".strip(),
            ),
            "results": _first_str(rec.get("Results"), codes),
            "source": "personator",
        }
    if last.get("results") and _is_auth_fail(last["results"]):
        _auth_failed = True
    return last


def _lookup_property(address: str, city: str, state: str, zipc: str) -> dict:
    global _auth_failed
    last = {}
    for key in _key_variants():
        params = {
            "id": key,
            "t": "helios",
            "format": "JSON",
            "a1": address,
            "city": city,
            "state": state,
            "postal": zipc,
            "cols": "GrpPrimaryOwner,GrpOwnerAddress,GrpPropertySize,GrpPropertyUseInfo",
        }
        try:
            data = _get(PROPERTY, params)
        except Exception:
            continue
        codes = str(data.get("TransmissionResults") or "")
        _note(codes)
        if _is_auth_fail(codes) or "GE08" in codes:
            last = {"results": codes, "source": "property"}
            continue
        recs = data.get("Records") or []
        rec = recs[0] if recs else {}
        owner = rec.get("PrimaryOwner") or {}
        oaddr = rec.get("OwnerAddress") or {}
        size = rec.get("PropertySize") or {}
        use = rec.get("PropertyUseInfo") or {}
        _remember_key(key)
        return {
            "owner_name": _first_str(owner.get("Name1Full"), owner.get("Name1First") and f"{owner.get('Name1First','')} {owner.get('Name1Last','')}".strip()),
            "owner_occupied": str(oaddr.get("OwnerOccupied") or "") in ("1", "Y", "y", "true", "True"),
            "sqft": _first_str(size.get("AreaBuilding"), size.get("AreaBuildingDefinition")),
            "year_built": _first_str(use.get("YearBuilt")),
            "zip": _first_str(oaddr.get("Zip"), zipc).split("-")[0],
            "email": "",
            "phone": "",
            "results": _first_str(rec.get("Results"), codes),
            "source": "property",
        }
    if last.get("results") and _is_auth_fail(last["results"]):
        _auth_failed = True
    return last


def ping() -> dict:
    if not configured():
        return {"ok": False, "error": "missing key"}
    results = {}
    for i, key in enumerate(_key_variants()):
        try:
            data = _get(
                CONSUMER,
                {
                    "id": key,
                    "act": "Check",
                    "format": "JSON",
                    "a1": "22382 Avenida Empresa",
                    "city": "Rancho Santa Margarita",
                    "state": "CA",
                    "postal": "92688",
                },
            )
            codes = str(data.get("TransmissionResults") or "")
            rec = (data.get("Records") or [{}])[0]
            rec_codes = str(rec.get("Results") or "")
            results[f"key{i}"] = (codes or rec_codes or "ok")
            if not _is_auth_fail(codes) and "GE29" not in codes:
                _remember_key(key)
                return {"ok": True, "transmission": codes or "ok", "record": rec_codes, **results}
        except Exception as e:
            results[f"key{i}"] = str(e)
    return {"ok": False, **results, "last_code": _last_code}


def append_contact(row: dict) -> dict:
    global _auth_failed
    if not configured() or _auth_failed:
        return row
    if _real_email(row.get("email") or ""):
        return row
    address = (row.get("address") or "").strip()
    if not address or address.lower().startswith("near "):
        return row
    city = (row.get("city") or "").strip()
    state = (row.get("state") or "TX").strip() or "TX"
    zipc = (row.get("zip") or "").strip()
    if not city and not zipc:
        return row
    key = _cache_key(address, city, state, zipc)
    cached = _cache_get(key)
    if cached is not None:
        return _apply(row, cached)

    hit = _lookup_property(address, city, state, zipc)
    if _auth_failed:
        return row

    if not _append_blocked and not _real_email(hit.get("email") or ""):
        appended = _personator_get("Append", address, city, state, zipc, opt="Append:blank")
        if _real_email(appended.get("email") or ""):
            hit["email"] = appended["email"]
        if appended.get("phone") and not hit.get("phone"):
            hit["phone"] = appended["phone"]
        if appended.get("owner_name") and not hit.get("owner_name"):
            hit["owner_name"] = appended["owner_name"]
        if appended.get("results"):
            hit["results"] = (hit.get("results") or "") + "," + appended["results"]

    _cache_set(key, hit)
    return _apply(row, hit)
