import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
from . import db

load_dotenv()

SUBJECT = "{name}, your {city} home may qualify for solar + VPP"

BODY = """Hi {name},

I work with homeowners in {tdu} territory on solar and the Texas virtual power plant program.

Your property at {address} in {county} County looks like a fit:
- Owner-occupied single-family
- About {sqft} sq ft, built {year}
- Roof looks suitable for roughly {kw} kW
{ec}

Interested homeowners typically lower their electric bill and can earn from the VPP battery program. If you want a no-pressure look at your numbers, just reply to this email.

{signoff}
"""


def render(lead: dict) -> tuple[str, str]:
    ec = "- This address is in a 2026 Energy Community (extra federal adder)." if lead.get("energy_community") else "- Eligible deregulated market (Solrite VPP)."
    name = lead.get("first_name") or "there"
    subj = SUBJECT.format(name=name, city=lead.get("city") or "Texas")
    body = BODY.format(
        name=name,
        tdu=lead.get("tdu") or "your",
        address=lead.get("address") or "your home",
        county=lead.get("county") or "",
        sqft=f"{lead.get('sqft') or '—'}",
        year=lead.get("year_built") or "1995+",
        kw=lead.get("kw_potential") or "10–26",
        ec=ec,
        signoff=os.getenv("FROM_NAME") or "Solar team",
    )
    return subj, body


def send_one(lead: dict) -> str:
    to = (lead.get("email") or "").strip()
    if not to:
        return "no_email"
    subj, body = render(lead)
    user, pw = os.getenv("SMTP_USER"), os.getenv("SMTP_PASS")
    if not user or not pw:
        db.log_message(lead["id"], subj, body, "preview")
        return "preview"
    msg = EmailMessage()
    msg["Subject"] = subj
    msg["From"] = f"{os.getenv('FROM_NAME')} <{os.getenv('FROM_EMAIL') or user}>"
    msg["To"] = to
    if os.getenv("REPLY_TO"):
        msg["Reply-To"] = os.getenv("REPLY_TO")
    msg.set_content(body)
    with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", 587))) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(msg)
    db.log_message(lead["id"], subj, body, "sent")
    db.set_status(lead["id"], "contacted")
    return "sent"


def send_campaign(limit=50) -> dict:
    leads = db.list_leads(qualified=True, limit=500)
    pending = [l for l in leads if l.get("status") in ("new", None) and l.get("email")][:limit]
    results = []
    for l in pending:
        results.append({"id": l["id"], "email": l["email"], "result": send_one(l)})
    return {"sent": sum(1 for r in results if r["result"] == "sent"), "preview": sum(1 for r in results if r["result"] == "preview"), "results": results}
