"""Loans tracked as an EMI schedule: a fixed EMI from a first month to a last month."""
import csv
import re
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS loans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lender      TEXT NOT NULL,
    name        TEXT NOT NULL,
    principal   REAL,
    rate        REAL,
    emi         REAL NOT NULL,
    first_month TEXT NOT NULL,
    last_month  TEXT NOT NULL,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS loan_payments (
    loan_id INTEGER NOT NULL,
    month   TEXT NOT NULL,
    PRIMARY KEY (loan_id, month)
);
"""


def ensure(conn):
    conn.executescript(SCHEMA)
    if "separate" not in {r["name"] for r in conn.execute("PRAGMA table_info(loans)")}:
        conn.execute("ALTER TABLE loans ADD COLUMN separate INTEGER NOT NULL DEFAULT 0")


def _month(text: str) -> str:
    return datetime.strptime(text.strip(), "%Y-%m").strftime("%Y-%m")


def _principal(text: str):
    m = re.match(r"\s*([\d.,]+)\s*(L)?", text, re.I)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    return round(value * 100000) if m.group(2) else value


def _split_name(label: str):
    """'Ps5 pro (102960 @ 14.88%)' -> ('Ps5 pro', 102960.0, 14.88)"""
    m = re.match(r"(.*?)\s*\((.*)\)\s*$", label)
    if not m:
        return label.strip(), None, None
    name, inside = m.group(1).strip(), m.group(2)
    amount, _, rate = inside.partition("@")
    rate_match = re.search(r"[\d.]+", rate)
    return name, _principal(amount), float(rate_match.group()) if rate_match else None


def parse_csv(path):
    """Rows of the schedule sheet -> loans. Returns (loans, problems)."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.reader(fh) if r and r[0].strip()]
    months = [datetime.strptime(h.strip(), "%Y %B").strftime("%Y-%m") for h in rows[0][1:]]
    loans, problems, lender, totals = [], [], "Other", None
    for row in rows[1:]:
        label = row[0].strip()
        if label.startswith("#"):
            lender = label.lstrip("# ").strip()
            continue
        cells = [(months[i], float(v)) for i, v in enumerate(row[1:]) if i < len(months) and v.strip()]
        if label.lower() == "total":
            totals = dict(cells)
            continue
        if not cells:
            problems.append(f"{label}: no EMI amounts, skipped")
            continue
        name, principal, rate = _split_name(label)
        # A row with no "(amount @ rate)" is not part of the lender group above it.
        own_lender = lender if "(" in label else "Other"
        amounts = {a for _, a in cells}
        span = months[months.index(cells[0][0]) : months.index(cells[-1][0]) + 1]
        if len(amounts) > 1 or len(span) != len(cells):
            problems.append(f"{label}: EMI varies or has gaps; imported as {cells[0][1]:.0f} for the whole range")
        loans.append({
            "lender": own_lender, "name": name, "principal": principal, "rate": rate,
            "emi": cells[0][1], "first_month": cells[0][0], "last_month": cells[-1][0],
            "open_ended": cells[-1][0] == months[-1],
        })
    if totals:
        for month, expected in totals.items():
            got = sum(l["emi"] for l in loans if l["first_month"] <= month <= l["last_month"])
            if abs(got - expected) > 0.5:
                problems.append(f"{month}: sheet total {expected:.0f} but loans add up to {got:.0f}")
    return loans, problems


def import_csv(conn, path, replace=False):
    ensure(conn)
    loans, problems = parse_csv(path)
    if replace:
        conn.execute("DELETE FROM loans")
    for l in loans:
        conn.execute(
            "INSERT INTO loans(lender, name, principal, rate, emi, first_month, last_month, note) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (l["lender"], l["name"], l["principal"], l["rate"], l["emi"], l["first_month"], l["last_month"],
             "Schedule sheet ends here; the loan may run longer." if l["open_ended"] else None),
        )
    conn.commit()
    return loans, problems


def all_loans(conn) -> list:
    ensure(conn)
    return [dict(r) for r in conn.execute("SELECT * FROM loans ORDER BY id")]


def _text(value, limit, required=True) -> str:
    value = " ".join(str(value or "").split())
    if (required and not value) or len(value) > limit:
        raise ValueError(f"text must be {'1' if required else '0'} to {limit} characters")
    return value


def _number(value, required=False):
    if value in (None, ""):
        if required:
            raise ValueError("EMI is required")
        return None
    number = float(value)
    if not 0 <= number < 1e10:
        raise ValueError("numbers must be zero or more")
    return number


def save(conn, item):
    ensure(conn)
    first, last = _month(item["first_month"]), _month(item["last_month"])
    if last < first:
        raise ValueError("last EMI month is before the first")
    values = (
        _text(item["lender"], 40), _text(item["name"], 60), _number(item.get("principal")),
        _number(item.get("rate")), _number(item["emi"], required=True), first, last,
        _text(item.get("note"), 200, required=False) or None,
        int(bool(item.get("separate"))),
    )
    if item.get("id"):
        cur = conn.execute(
            "UPDATE loans SET lender=?, name=?, principal=?, rate=?, emi=?, first_month=?, last_month=?, note=?, separate=? "
            "WHERE id=?",
            values + (int(item["id"]),),
        )
        if cur.rowcount == 0:
            raise ValueError("unknown loan")
    else:
        conn.execute(
            "INSERT INTO loans(lender, name, principal, rate, emi, first_month, last_month, note, separate) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
    conn.commit()


def payments(conn) -> list:
    ensure(conn)
    return [dict(r) for r in conn.execute("SELECT loan_id, month FROM loan_payments")]


def set_paid(conn, loan_ids, month, paid):
    """Tick or untick one month's EMI for the given loans."""
    ensure(conn)
    month = _month(month)
    for loan_id in loan_ids:
        if paid:
            conn.execute("INSERT OR IGNORE INTO loan_payments(loan_id, month) VALUES(?, ?)", (int(loan_id), month))
        else:
            conn.execute("DELETE FROM loan_payments WHERE loan_id = ? AND month = ?", (int(loan_id), month))
    conn.commit()


def delete(conn, loan_id):
    ensure(conn)
    conn.execute("DELETE FROM loan_payments WHERE loan_id = ?", (int(loan_id),))
    conn.execute("DELETE FROM loans WHERE id = ?", (int(loan_id),))
    conn.commit()
