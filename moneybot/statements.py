"""Statements requested from PhonePe (and later banks): stored as received, then checked against the ledger on rebuild."""
import csv
import io
import re
import subprocess
from datetime import datetime

from pypdf import PdfReader

from .parsers import _split_axis_info

MAX_SIZE = 5_000_000
PIN_SERVICES = {"Axis": "moneybot-statement-axis", "ICICI": "moneybot-statement-icici"}
COLUMNS = {"Date", "Time", "Transaction Details", "Transaction ID", "UTR", "Transaction Type",
           "Credit/debit instrument", "Amount"}
PARTY = re.compile(r"^(?:Paid to|Received from)\s+(.+)$")
ICICI_UPI = re.compile(r"^UPI/(?!P2[AM]/)([^/]+)/")


def payee_of(details: str) -> str:
    details = " ".join(details.split())
    m = PARTY.match(details) or ICICI_UPI.match(details)
    return m.group(1).strip() if m else _split_axis_info(details)["payee"]


def parse_phonepe(text: str) -> tuple:
    """CSV text -> (period, rows). Raises ValueError rather than importing part of a file it cannot read."""
    lines = text.lstrip("﻿").splitlines()
    head = next((i for i, line in enumerate(lines) if line.startswith("Date,Time,")), None)
    if head is None:
        raise ValueError("no transaction table in this file")
    period = next((line.split(",", 1)[1].strip() for line in lines[:head] if line.startswith("Duration,")), "")
    table = csv.DictReader(lines[head:])
    if not COLUMNS <= set(table.fieldnames or []):
        raise ValueError("the statement columns have changed")
    rows = []
    for raw in table:
        # The notes under the table have no date.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", (raw["Date"] or "").strip()):
            continue
        try:
            moment = datetime.strptime(f"{raw['Date'].strip()} {raw['Time'].strip()}", "%Y-%m-%d %H:%M")
            amount = float(raw["Amount"].replace(",", ""))
            direction = {"Debit": "debit", "Credit": "credit"}[raw["Transaction Type"].strip()]
        except (AttributeError, KeyError, ValueError):
            raise ValueError(f"could not read the row dated {raw['Date']}") from None
        txn_id = (raw["Transaction ID"] or "").strip()
        if not txn_id or amount <= 0:
            raise ValueError(f"could not read the row dated {raw['Date']}")
        rows.append({
            "txn_id": txn_id, "ts": int(moment.timestamp()), "direction": direction, "amount": amount,
            "details": " ".join(raw["Transaction Details"].split()), "utr": (raw["UTR"] or "").strip(),
            "instrument": (raw["Credit/debit instrument"] or "").strip(),
        })
    return period, rows


def _money(text: str) -> float:
    return float(text.replace(",", ""))


def parse_axis(text: str) -> tuple:
    """Statement text -> (period, rows). The text does not show which column an amount was in, so the running
    balance decides debit or credit. Any row that does not add up rejects the whole file."""
    opening = re.search(r"OPENING BALANCE\s+(-?[\d,]+\.\d{2})", text)
    closing = re.search(r"CLOSING BALANCE\s+(-?[\d,]+\.\d{2})", text)
    totals = re.search(r"TRANSACTION TOTAL\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})", text)
    account = re.search(r"Statement of Account No :\s*(\d+)", text)
    if not (opening and closing and totals and account):
        raise ValueError("this is not the usual Axis statement layout")
    period = re.search(r"From : ([\d-]+)\s+To : ([\d-]+)", text)
    instrument = "XXXX" + account.group(1)[-6:]
    balance = _money(opening.group(1))
    spent = received = 0.0
    rows = []
    for entry in re.split(r"(?m)^(?=\d{2}-\d{2}-\d{4}\b)", text[opening.end():closing.start()])[1:]:
        flat = " ".join(entry.split())
        # Page-end text can follow the last row of a page, so this is not anchored to the end.
        m = re.search(r"([\d,]+\.\d{2}) (-?[\d,]+\.\d{2}) \d{3,4}\b", flat)
        if not m:
            raise ValueError(f"could not read the row dated {flat[:10]}")
        amount, after = _money(m.group(1)), _money(m.group(2))
        if abs(abs(after - balance) - amount) > 0.005:
            raise ValueError(f"the balance does not add up at the row dated {flat[:10]}")
        direction = "credit" if after > balance else "debit"
        if direction == "credit":
            received += amount
        else:
            spent += amount
        balance = after
        details = flat[10:m.start()].strip()
        day = datetime.strptime(flat[:10], "%d-%m-%Y")
        rows.append({
            # The statement has no id of its own; the balance after a row tells apart equal payments on one day.
            "txn_id": f"axis:{account.group(1)[-6:]}:{day:%Y-%m-%d}:{after:.2f}:{amount:.2f}",
            "ts": int(day.replace(hour=12).timestamp()), "direction": direction, "amount": amount,
            "details": details, "utr": _split_axis_info(details)["ref"] or "", "instrument": instrument,
        })
    if abs(balance - _money(closing.group(1))) > 0.005 or abs(spent - _money(totals.group(1))) > 0.005 \
            or abs(received - _money(totals.group(2))) > 0.005:
        raise ValueError("the rows do not add up to the statement's totals")
    return (f"{period.group(1)} to {period.group(2)}" if period else ""), rows


def parse_icici(text: str) -> tuple:
    """Statement text -> (period, rows). As with Axis, the running balance decides debit or credit."""
    account = re.search(r"Savings Account Number:\s*(\d+)", text)
    period = re.search(r"for the period (.+? - .+?\d{4})", text)
    start = re.search(r"\d{2}-\d{2}-\d{4}\s+B/F\s+(-?[\d,]+\.\d{2})", text)
    totals = re.search(
        r"^TOTAL\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})", text[start.end():] if start else "", re.M
    )
    if not (account and start and totals):
        raise ValueError("this is not the usual ICICI statement layout")
    instrument = "XXXX" + account.group(1)[-6:]
    balance = _money(start.group(1))
    received = spent = 0.0
    rows = []
    for entry in re.split(r"(?m)^(?=\d{2}-\d{2}-\d{4}\b)", text[start.end():start.end() + totals.start()])[1:]:
        flat = " ".join(entry.split())
        m = re.search(r"([\d,]+\.\d{2}) (-?[\d,]+\.\d{2})(?: |$)", flat)
        if not m:
            raise ValueError(f"could not read the row dated {flat[:10]}")
        amount, after = _money(m.group(1)), _money(m.group(2))
        if abs(abs(after - balance) - amount) > 0.005:
            raise ValueError(f"the balance does not add up at the row dated {flat[:10]}")
        direction = "credit" if after > balance else "debit"
        if direction == "credit":
            received += amount
        else:
            spent += amount
        balance = after
        details = flat[10:m.start()].strip()
        reference = re.search(r"/(\d{12})/", details) if details.startswith("UPI/") else None
        day = datetime.strptime(flat[:10], "%d-%m-%Y")
        rows.append({
            "txn_id": f"icici:{account.group(1)[-6:]}:{day:%Y-%m-%d}:{after:.2f}:{amount:.2f}",
            "ts": int(day.replace(hour=12).timestamp()), "direction": direction, "amount": amount,
            "details": details[:120], "utr": reference.group(1) if reference else "", "instrument": instrument,
        })
    if abs(received - _money(totals.group(1))) > 0.005 or abs(spent - _money(totals.group(2))) > 0.005 \
            or abs(balance - _money(totals.group(3))) > 0.005:
        raise ValueError("the rows do not add up to the statement's totals")
    return (period.group(1) if period else ""), rows


def _pin(source: str) -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", PIN_SERVICES[source], "-w"], capture_output=True, text=True
    )
    pin = result.stdout.strip()
    if result.returncode != 0 or not pin:
        raise ValueError(f"the {source} statement PIN is not saved in the Keychain")
    return pin


def _pdf_text(content: bytes, source: str) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(_pin(source)):
            raise ValueError("the saved PIN did not open it")
        return "\n".join(page.extract_text() for page in reader.pages)
    except ValueError:
        raise
    except Exception:
        raise ValueError("the PDF could not be opened") from None


def _read_axis(content: bytes) -> tuple:
    return parse_axis(_pdf_text(content, "Axis"))


def _read_icici(content: bytes) -> tuple:
    return parse_icici(_pdf_text(content, "ICICI"))


def _read_phonepe(content: bytes) -> tuple:
    return parse_phonepe(content.decode("utf-8-sig", errors="replace"))


READERS = {"PhonePe": _read_phonepe, "Axis": _read_axis, "ICICI": _read_icici}


def store(conn, email_id, source, filename, received_ts, content):
    """Keep one statement file. A file that cannot be read is recorded, so the user hears about it."""
    period, rows, error = "", [], None
    try:
        if content is None:
            raise ValueError("the expected file is not attached (PhonePe statements must be requested as CSV)")
        if len(content) > MAX_SIZE:
            raise ValueError("the file is too large")
        period, rows = READERS[source](content)
    except ValueError as exc:
        error = str(exc)
    conn.execute(
        "INSERT OR REPLACE INTO statement_files(email_id, source, filename, received_ts, period, row_count, error) "
        "VALUES(?, ?, ?, ?, ?, ?, ?)",
        (email_id, source, filename, received_ts, period, len(rows), error),
    )
    # The same payment appears again in overlapping statements; the first copy is kept.
    conn.executemany(
        "INSERT OR IGNORE INTO statement_rows(txn_id, email_id, source, ts, direction, amount, details, utr, instrument) "
        "VALUES(:txn_id, :email_id, :source, :ts, :direction, :amount, :details, :utr, :instrument)",
        [{**r, "email_id": email_id, "source": source} for r in rows],
    )
    conn.commit()


def summaries(conn) -> list:
    """Statements the user has not dismissed yet, newest first, with what checking them found."""
    out = []
    for position, f in enumerate(
        conn.execute("SELECT * FROM statement_files WHERE seen = 0 ORDER BY received_ts DESC").fetchall()
    ):
        counts = dict(conn.execute(
            "SELECT r.outcome, COUNT(*) FROM statement_results r JOIN statement_rows s USING (txn_id) "
            "WHERE s.email_id = ? GROUP BY r.outcome", (f["email_id"],)
        ).fetchall())
        # An older statement that a newer one fully overlaps has nothing of its own to report.
        if position and not f["error"] and not set(counts) - {"early"}:
            continue
        details = conn.execute(
            "SELECT r.outcome, s.ts, s.details, s.amount, t.payee AS entry, t.account FROM statement_results r "
            "JOIN statement_rows s USING (txn_id) LEFT JOIN transactions t ON t.key = r.matched_key "
            "WHERE s.email_id = ? AND r.outcome IN ('manual', 'deleted') ORDER BY s.ts", (f["email_id"],)
        ).fetchall()
        out.append({
            "id": f["email_id"], "source": f["source"], "period": f["period"], "received_ts": f["received_ts"],
            "error": f["error"], "rows": f["row_count"], "added": counts.get("added", 0),
            "known": counts.get("known", 0), "manual": counts.get("manual", 0), "early": counts.get("early", 0),
            "deleted": counts.get("deleted", 0),
            "matched": [dict(d) for d in details if d["outcome"] == "manual"],
            "removed": [dict(d) for d in details if d["outcome"] == "deleted"],
        })
    return out


def mark_seen(conn):
    conn.execute("UPDATE statement_files SET seen = 1")
    conn.commit()
