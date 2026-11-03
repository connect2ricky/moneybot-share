"""Credit card statements, kept apart from the ledger: nothing here reaches spending or budgets."""
import re
import subprocess
from datetime import datetime
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import _font

# Axis statements carry a font with one width more than pypdf allows.
_font.MAX_SIMPLE_FONT_CHARACTER_CODE = 256

# Statement totals are rounded differently from their rows by some banks.
TOLERANCE = 1.5

AMOUNT = r"[\d,]+\.\d\d"


class CardStatementError(ValueError):
    pass


def clean(text: str) -> str:
    return text.replace("\xa0", " ")


def _money(text: str) -> float:
    return float(text.replace(",", ""))


def _date(text: str, *formats) -> str:
    text = " ".join(text.split())
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise CardStatementError(f"unexpected date: {text}")


def _need(pattern, text, flags=re.M):
    m = re.search(pattern, text, flags)
    if m is None:
        raise CardStatementError(f"statement layout not recognised: {pattern[:40]}")
    return m


def parse_axis(text: str) -> dict:
    m = _need(
        rf"Statement Generation Date\n(\d\d/\d\d/\d{{4}}) - (\d\d/\d\d/\d{{4}}) (\d\d/\d\d/\d{{4}}) "
        rf"(\d\d/\d\d/\d{{4}})({AMOUNT})\s+(Dr|Cr)?\s*({AMOUNT})",
        text,
    )
    fmt = "%d/%m/%Y"
    total = _money(m[5]) * (-1 if m[6] == "Cr" else 1)
    limits = _need(rf"\*{{6}}(\d{{4}}) ({AMOUNT}) ({AMOUNT})", text)
    summary = _need(rf"=Total Payment Due\n({AMOUNT})\s+(Dr|Cr)?", text)
    rows = []
    for r in re.finditer(rf"^(\d\d/\d\d/\d{{4}}) (.+?)\s+({AMOUNT}) (Dr|Cr)\s*$", text, re.M):
        details = re.split(r"\s{2,}", r[2].strip())[0]
        rows.append({"date": _date(r[1], fmt), "details": details, "amount": _money(r[3]), "credit": r[4] == "Cr"})
    return {
        "last4": limits[1], "period_start": _date(m[1], fmt), "period_end": _date(m[2], fmt),
        "statement_date": _date(m[4], fmt), "due_date": _date(m[3], fmt), "total_due": total, "min_due": _money(m[7]),
        "previous": _money(summary[1]) * (-1 if summary[2] == "Cr" else 1),
        "credit_limit": _money(limits[2]), "available": _money(limits[3]), "rows": rows,
    }


def parse_hdfc(text: str) -> dict:
    m = _need(rf"TOTAL AMOUNT DUE\s+C({AMOUNT})\s+MINIMUM DUE\s+C({AMOUNT})\s+DUE DATE\s+(\d\d \w+, \d{{4}})", text)
    fmt = "%d %b, %Y"
    period = _need(r"(\d\d \w+, \d{4})\n(\d\d \w+, \d{4}) - (\d\d \w+, \d{4})", text)
    summary = _need(rf"FINANCE CHARGES\s+C({AMOUNT})", text)
    limits = _need(r"AVAILABLE CASH LIMIT\s+C([\d,]+) C([\d,]+)", text)
    rows = []
    pattern = rf"^(\d\d/\d\d/\d{{4}}) ?\| ?\d\d:\d\d (.+?)\s+(?:([+-])\s*(\d*)\s+)?C ?({AMOUNT})(?: l)?\s*$"
    for r in re.finditer(pattern, text, re.M):
        rows.append({"date": _date(r[1], "%d/%m/%Y"), "details": " ".join(r[2].split()),
                     "amount": _money(r[5]), "credit": r[3] == "+" and not r[4]})
    loans = {r[1]: int(r[2]) for r in re.finditer(r"^\s*(\d{6,}) \d\d/\d\d/\d{4} C[\d,.]+ (\d+) Months", text, re.M)}
    return {
        "loans": loans, "last4": _need(r"\d{6}X{6}(\d{4})", text)[1], "period_start": _date(period[2], fmt),
        "period_end": _date(period[3], fmt), "statement_date": _date(period[1], fmt), "due_date": _date(m[3], fmt),
        "total_due": _money(m[1]), "min_due": _money(m[2]), "previous": _money(summary[1]),
        "credit_limit": _money(limits[1]), "available": _money(limits[2]), "rows": rows,
    }


def parse_indusind(text: str) -> dict:
    head = _need(
        rf"^ ({AMOUNT}) (DR|CR)?\s*\n ({AMOUNT})\n ({AMOUNT})\n ({AMOUNT})\n (\d\d/\d\d/\d{{4}})\n"
        rf" (\d\d/\d\d/\d{{4}}) To (\d\d/\d\d/\d{{4}})\n (\d\d/\d\d/\d{{4}})\n ({AMOUNT}) ({AMOUNT})",
        text,
    )
    due = _need(rf"^ ({AMOUNT}) (DR|CR)?\s*\n ({AMOUNT})\n ({AMOUNT}) (?:DR|CR)?\s*\n(?:MR|MS|MRS)", text)
    fmt = "%d/%m/%Y"
    rows = []
    # A long merchant category wraps, so a row can run over several lines.
    pattern = rf"^(\d\d/\d\d/\d{{4}}) ((?:(?!^\d\d/\d\d/).)+?)\s+(-?\d+) ({AMOUNT}) (DR|CR)\s*$"
    for r in re.finditer(pattern, text, re.M | re.S):
        rows.append({"date": _date(r[1], fmt), "details": " ".join(r[2].split()),
                     "amount": _money(r[4]), "credit": r[5] == "CR"})
    return {
        "last4": _need(r"\d{4}X{8}(\d{4})", text)[1], "period_start": _date(head[7], fmt),
        "period_end": _date(head[8], fmt), "statement_date": _date(head[9], fmt), "due_date": _date(head[6], fmt),
        "total_due": _money(due[1]) * (-1 if due[2] == "CR" else 1), "min_due": _money(due[3]),
        "previous": _money(head[1]) * (-1 if head[2] == "CR" else 1),
        "credit_limit": _money(head[10]), "available": _money(head[11]), "rows": rows,
    }


def parse_icici(text: str) -> dict:
    fmt = "%B %d, %Y"
    amount = rf"`({AMOUNT})"
    # The two figures swap places between statements; the total is never the smaller.
    dues = sorted(_money(x) for x in _need(rf"{amount}\s+{amount}\s+SPENDS OVERVIEW", text).groups())
    dates = _need(r"^(\w+ \d+, \d{4})\s*\n(\w+ \d+, \d{4})\s*$", text)
    period = _need(r"Statement period : (\w+ \d+, \d{4}) to (\w+ \d+, \d{4})", text)
    summary = _need(rf"Payments / Credits\s+{amount}", text)
    limits = _need(rf"Available Cash\s+{amount} {amount}", text)
    rows = []
    for r in re.finditer(rf"^(\d\d/\d\d/\d{{4}}) (\d{{8,}}) (.+?) (-?\d+)(?: [\d,]+\.\d\d)? ({AMOUNT})( CR)?\s*$", text, re.M):
        rows.append({"date": _date(r[1], "%d/%m/%Y"), "details": " ".join(r[3].split()),
                     "amount": _money(r[5]), "credit": bool(r[6])})
    return {
        "last4": _need(r"\d{4}X{8}(\d{4})", text)[1], "period_start": _date(period[1], fmt),
        "period_end": _date(period[2], fmt), "statement_date": _date(dates[1], fmt), "due_date": _date(dates[2], fmt),
        "total_due": dues[1], "min_due": dues[0], "previous": _money(summary[1]),
        "credit_limit": _money(limits[1]), "available": _money(limits[2]), "rows": rows,
    }


# Only rows carrying an instalment number are EMIs: HDFC also writes "EMI" in front of ordinary purchases.
_HDFC_EMI = re.compile(r"^(OFFUS EMI|SMARTEMI|MER EMI)\s*,\s*(PRIN|INT) NB?R?:(\d+),0*(\d+)", re.I)
_HDFC_MERCHANT_EMI = re.compile(r"^EMI M-(\d+)M (.+?),P:(\d+),0*(\d+)", re.I)
_AXIS_EMI = re.compile(r"^EMI (PRINCIPAL|INTEREST) - (\d+)/(\d+), REF# (\d+)", re.I)
_ICICI_EMI = re.compile(r"^(Principal|Interest) Amount Amortization - <(\d+)/(\d+)>", re.I)
_INDUSIND_EMI = re.compile(r"^EMI (PRIN FOR|INT-)\s*(.+?) \((\d+)/(\d+)\)", re.I)


_PAYMENT = re.compile(r"PAYMENT|^BPPY", re.I)
_GST = re.compile(r"^[CSI]?GST\b", re.I)
_IGST = re.compile(r"^IGST\b", re.I)
GST_RATE = 0.18


def _instalment(details: str) -> dict | None:
    """What an EMI row says about itself: principal or interest, its number, and its plan where stated."""
    if m := _HDFC_EMI.match(details):
        plain = {"OFFUS EMI": "Purchase EMI", "SMARTEMI": "SmartEMI", "MER EMI": "Merchant EMI"}[m[1].upper()]
        return {"key": m[4], "loan": m[4], "name": plain, "part": m[2].upper()[:3], "number": int(m[3]), "tenure": None}
    if m := _HDFC_MERCHANT_EMI.match(details):
        return {"key": m[4], "loan": m[4], "name": m[2].title(), "part": "PRI", "number": int(m[3]), "tenure": int(m[1])}
    if m := _AXIS_EMI.match(details):
        return {"key": m[4], "loan": m[4], "name": "EMI", "part": m[1].upper()[:3], "number": int(m[2]), "tenure": int(m[3])}
    if m := _ICICI_EMI.match(details):
        return {"key": m[2] + "/" + m[3], "loan": None, "name": "EMI", "part": m[1].upper()[:3],
                "number": int(m[2]), "tenure": int(m[3])}
    if m := _INDUSIND_EMI.match(details):
        return {"key": m[2][:10] + m[3] + "/" + m[4], "loan": None, "name": re.sub(r"\s+PRIV.*$", "", m[2], flags=re.I).title(),
                "part": "PRI" if m[1].upper().startswith("PRIN") else "INT", "number": int(m[3]), "tenure": int(m[4])}
    return None


def _charge_gst(rows: list, out: list, previous: list):
    """Add GST to the EMI it belongs to, found by being 18% of an interest charge.

    Most banks bill it with the interest. HDFC bills it on the next statement, so that one's interest counts too.
    GST on anything else, such as fees, is counted with the EMIs in an entry of its own.
    """
    current = [(e, e) for e in out]
    earlier = [(e, next((c for c in out if c["key"] == e["key"]), None)) for e in previous if e["number"]]
    open_charges = [(source, owner) for source, owner in current + earlier if source["interest"] > 0]
    for row in rows:
        if row["credit"] or row["emi"] or not _GST.search(row["details"]):
            continue
        match = next(
            (c for c in open_charges if abs(round(c[0]["interest"] * GST_RATE, 2) - row["amount"]) <= 0.02), None
        )
        if match is None:
            fees = next((e for e in out if e["key"] == "fees"), None)
            if fees is None:
                fees = {"key": "fees", "name": "GST on fees", "number": None, "tenure": None, "left": None,
                        "principal": 0.0, "interest": 0.0, "gst": 0.0, "amount": 0.0}
                out.append(fees)
            fees["gst"] = round(fees["gst"] + row["amount"], 2)
            fees["amount"] = round(fees["amount"] + row["amount"], 2)
            row["emi"], row["emi_number"] = True, "GST"
            continue
        open_charges.remove(match)
        source, owner = match
        if owner is None:  # the last instalment was on the statement before
            owner = {**source, "left": 0, "principal": 0.0, "interest": 0.0, "gst": 0.0, "amount": 0.0}
            out.append(owner)
        owner["gst"] = round(owner["gst"] + row["amount"], 2)
        owner["amount"] = round(owner["amount"] + row["amount"], 2)
        row["emi"] = True
        row["emi_number"] = f"{source['number']}/{source['tenure']}" if source["tenure"] else str(source["number"])


def emis(rows: list, tenures: dict, previous: tuple = ()) -> list:
    """Mark a statement's EMI rows and return one entry per plan: principal, interest and the GST on it."""
    plans = {}
    for row in rows:
        found = None if row["credit"] else _instalment(row["details"])
        row["emi"] = found is not None
        if found is None:
            continue
        # HDFC cuts the loan number short on merchant EMIs.
        key = next((p for p in plans if p.startswith(found["key"]) or found["key"].startswith(p)), found["key"])
        if len(found["key"]) > len(key):
            plans[found["key"]] = plans.pop(key)
            key = found["key"]
        plan = plans.setdefault(key, {"name": found["name"], "loan": found["loan"], "number": found["number"],
                                      "tenure": found["tenure"], "principal": 0.0, "interest": 0.0, "rows": []})
        plan["rows"].append(row)
        plan["principal" if found["part"] == "PRI" else "interest"] += row["amount"]
        if found["name"] not in ("Merchant EMI", "EMI"):
            plan["name"] = found["name"]
        plan["tenure"] = plan["tenure"] or found["tenure"]
        plan["loan"] = found["loan"] if len(found["loan"] or "") > len(plan["loan"] or "") else plan["loan"]
    out = []
    for key, plan in plans.items():
        tenure = plan["tenure"] or tenures.get(plan["loan"])
        for row in plan["rows"]:
            row["emi_number"] = f"{plan['number']}/{tenure}" if tenure else str(plan["number"])
        out.append({
            "key": key, "name": plan["name"], "number": plan["number"], "tenure": tenure,
            "left": tenure - plan["number"] if tenure else None, "principal": round(plan["principal"], 2),
            "interest": round(plan["interest"], 2), "gst": 0.0,
            "amount": round(plan["principal"] + plan["interest"], 2),
        })
    _charge_gst(rows, out, previous)
    return sorted(out, key=lambda e: -e["amount"])


PARSERS = {"axis": parse_axis, "hdfc": parse_hdfc, "icici": parse_icici, "indusind": parse_indusind}
PASSWORD_SERVICES = {bank: f"moneybot-statement-{bank}-card" for bank in PARSERS}


def password(bank: str) -> str | None:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", PASSWORD_SERVICES[bank], "-w"], capture_output=True, text=True
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def read(content: bytes, bank: str, secret: str) -> dict | None:
    """The statement's figures and rows, or None for a file that is not a monthly statement."""
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(secret):
            raise CardStatementError("the saved password did not open it")
        text = clean("\n".join(page.extract_text() for page in reader.pages))
    except PdfReadError:
        raise CardStatementError("the PDF could not be opened") from None
    if "GLIMPSE OF HOW YOU SPENT" in text:  # IndusInd's yearly summary
        return None
    return PARSERS[bank](text)


def balanced(statement: dict) -> bool:
    """Whether the previous balance and the rows arrive at the total the bank states."""
    net = sum(-r["amount"] if r["credit"] else r["amount"] for r in statement["rows"])
    return abs(statement["previous"] + net - statement["total_due"]) <= TOLERANCE


def store(conn, email_id, card, received_ts, statement=None, error=None, skipped=False):
    conn.execute("DELETE FROM card_rows WHERE email_id = ?", (email_id,))
    conn.execute("DELETE FROM card_loans WHERE email_id = ?", (email_id,))
    s = statement or {}
    conn.execute(
        "INSERT OR REPLACE INTO card_statements(email_id, card, received_ts, last4, period_start, period_end, "
        "statement_date, due_date, total_due, min_due, previous, credit_limit, available, balanced, skipped, error) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (email_id, card, received_ts, s.get("last4"), s.get("period_start"), s.get("period_end"),
         s.get("statement_date"), s.get("due_date"), s.get("total_due"), s.get("min_due"), s.get("previous"),
         s.get("credit_limit"), s.get("available"), int(balanced(s)) if s else None, int(skipped), error),
    )
    conn.executemany(
        "INSERT INTO card_rows(email_id, seq, date, details, amount, credit) VALUES(?, ?, ?, ?, ?, ?)",
        [(email_id, i, r["date"], r["details"], r["amount"], int(r["credit"])) for i, r in enumerate(s.get("rows", []))],
    )
    conn.executemany(
        "INSERT INTO card_loans(email_id, loan, tenure) VALUES(?, ?, ?)",
        [(email_id, loan, tenure) for loan, tenure in s.get("loans", {}).items()],
    )
    conn.commit()


def add(conn, email_id, card, bank, received_ts, content, secret):
    """Store a downloaded statement. A file that cannot be read is kept as an error and tried again next sync."""
    try:
        statement = read(content, bank, secret)
    except CardStatementError as exc:
        return store(conn, email_id, card, received_ts, error=str(exc))
    store(conn, email_id, card, received_ts, statement, skipped=statement is None)


def summary(conn) -> dict:
    """Every statement, newest first, and which cards could not be read."""
    rows = {}
    for r in conn.execute("SELECT * FROM card_rows ORDER BY email_id, date, seq"):
        rows.setdefault(r["email_id"], []).append(
            {"date": r["date"], "details": r["details"], "amount": r["amount"], "credit": bool(r["credit"]),
             "payment": bool(r["credit"]) and _PAYMENT.search(r["details"]) is not None,
             "label": "GST" if _IGST.match(r["details"]) else r["details"]}
        )
    tenures = {r["loan"]: r["tenure"] for r in conn.execute("SELECT loan, tenure FROM card_loans")}
    statements, last = [], {}
    # Oldest first, because a statement can carry GST on the interest of the one before it.
    for s in conn.execute(
        "SELECT * FROM card_statements WHERE error IS NULL AND skipped = 0 ORDER BY statement_date, card"
    ):
        found = emis(rows.get(s["email_id"], []), tenures, last.get(s["card"], ()))
        last[s["card"]] = found
        others = round(s["total_due"] - sum(e["amount"] for e in found), 2)
        statements.append(
            {key: s[key] for key in ("card", "last4", "period_start", "period_end", "statement_date", "due_date",
                                     "total_due", "min_due", "previous", "credit_limit", "available")}
            | {"balanced": bool(s["balanced"]), "rows": rows.get(s["email_id"], []), "emis": found,
               # Banks round the total, which can leave a few paise.
               "others": 0.0 if abs(others) <= TOLERANCE else others}
        )
    statements.sort(key=lambda s: (s["statement_date"], s["card"]), reverse=True)
    problems = [
        {"card": r["card"], "message": r["error"], "count": r["n"]}
        for r in conn.execute(
            "SELECT card, error, COUNT(*) AS n FROM card_statements WHERE error IS NOT NULL GROUP BY card, error ORDER BY card"
        )
    ]
    return {"statements": statements, "problems": problems}
