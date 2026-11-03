"""Rebuild the transactions table from stored emails. Safe to run any number of times."""
import re
from collections import Counter, defaultdict
from datetime import datetime

from . import categories as cat
from . import db, statements
from .parsers import parse

PERSISTENT = """
CREATE TABLE IF NOT EXISTS payee_labels (
    payee_key TEXT PRIMARY KEY,
    category  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
    name TEXT PRIMARY KEY,
    grp  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deleted_txns (
    key     TEXT PRIMARY KEY,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS amount_overrides (
    key    TEXT PRIMARY KEY,
    amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    key  TEXT PRIMARY KEY,
    note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manual_txns (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      INTEGER NOT NULL,
    amount  REAL NOT NULL,
    payee   TEXT NOT NULL,
    account TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS category_renames (
    old TEXT PRIMARY KEY,
    new TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS field_overrides (
    key     TEXT PRIMARY KEY,
    payee   TEXT,
    date    TEXT,
    account TEXT
);
CREATE TABLE IF NOT EXISTS balance_anchors (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL,
    ts      INTEGER NOT NULL,
    amount  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS balance_excluded (
    account TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS subcategories (
    category TEXT NOT NULL,
    name     TEXT NOT NULL,
    PRIMARY KEY (category, name)
);
"""

REBUILT = """
DROP TABLE IF EXISTS movements;
CREATE TABLE movements (
    key       TEXT PRIMARY KEY,
    ts        INTEGER NOT NULL,
    account   TEXT NOT NULL,
    direction TEXT NOT NULL,
    amount    REAL NOT NULL
);
DROP TABLE IF EXISTS statement_results;
CREATE TABLE statement_results (
    txn_id      TEXT PRIMARY KEY,
    outcome     TEXT NOT NULL,
    matched_key TEXT
);
DROP TABLE IF EXISTS email_balances;
CREATE TABLE email_balances (
    account TEXT NOT NULL,
    ts      INTEGER NOT NULL,
    amount  REAL NOT NULL
);
DROP TABLE IF EXISTS transactions;
CREATE TABLE transactions (
    key         TEXT PRIMARY KEY,
    ts          INTEGER NOT NULL,
    date        TEXT NOT NULL,
    account     TEXT NOT NULL,
    direction   TEXT NOT NULL,
    amount      REAL NOT NULL,
    payee       TEXT,
    info        TEXT,
    channel     TEXT,
    ref         TEXT,
    app         TEXT,
    category    TEXT NOT NULL,
    subcategory TEXT,
    status      TEXT NOT NULL,
    counted     INTEGER NOT NULL,
    original_amount REAL,
    note        TEXT,
    bank_payee  TEXT
);
"""

POT_PREFIX = "Jupiter pot: "
POT_ACCOUNT = "Jupiter Smoke Savings"

# A hand-typed entry can be dated a little off from the real payment.
STATEMENT_MATCH_DAYS = 3

PROTECTED = {cat.UNCATEGORISED, cat.SELF_TRANSFER, "Ignored"}


def _has_table(conn, name) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def migrate(conn):
    conn.executescript(PERSISTENT)
    if "subcategory" not in {r["name"] for r in conn.execute("PRAGMA table_info(payee_labels)")}:
        conn.execute("ALTER TABLE payee_labels ADD COLUMN subcategory TEXT")
    renamed = _renames(conn)
    deleted = {r["name"] for r in conn.execute("SELECT name FROM deleted_categories")}
    conn.executemany(
        "INSERT OR IGNORE INTO categories(name, grp) VALUES(?, ?)",
        [(name, grp) for name, grp in cat.CATEGORIES.items() if name not in renamed and name not in deleted],
    )
    if not _has_table(conn, "txn_labels"):
        conn.execute(
            "CREATE TABLE txn_labels (key TEXT PRIMARY KEY, category TEXT NOT NULL, subcategory TEXT)"
        )
    conn.commit()


def _renames(conn) -> dict:
    return {r["old"]: r["new"] for r in conn.execute("SELECT old, new FROM category_renames")}


def category_groups(conn) -> dict:
    return {r["name"]: r["grp"] for r in conn.execute("SELECT name, grp FROM categories ORDER BY rowid")}


def subcategories(conn) -> dict:
    out = defaultdict(list)
    for r in conn.execute("SELECT category, name FROM subcategories ORDER BY rowid"):
        out[r["category"]].append(r["name"])
    return dict(out)


def _owner_name(conn) -> str:
    names = Counter()
    for row in conn.execute("SELECT body FROM emails WHERE sender = 'alerts@axis.bank.in'"):
        m = re.search(r"Dear (.+?),", row["body"] or "")
        if m:
            names[cat.payee_key(m.group(1))] += 1
    return names.most_common(1)[0][0] if names else ""


def _is_owner(payee: str, owner: str) -> bool:
    # Banks truncate names, so a long-enough prefix of the owner's name counts.
    key = cat.payee_key(payee)
    return bool(owner) and len(key) >= 9 and (owner.startswith(key) or key.startswith(owner))


def _resolve_account(hint: str, known: set, app: str) -> str:
    if hint:
        for account in sorted(known):
            digits = account.rsplit(" ", 1)[-1]
            if hint.endswith(digits) or digits.endswith(hint):
                return account
    return f"{app} UPI"


def _fold_statement_rows(conn, txns, known_accounts, start):
    """Add statement rows the ledger does not have yet. Each row ends up known, manual, deleted, added or early."""
    # In the order they arrived, so a new statement cannot change what an earlier one found.
    rows = conn.execute("SELECT * FROM statement_rows ORDER BY rowid").fetchall()
    own = {r["instrument"] for r in rows if r["instrument"]}
    known_accounts = known_accounts | {r["account"] for r in conn.execute("SELECT account FROM balance_anchors")}
    by_ref = {(t["ref"].lstrip("0"), t["direction"]): key for key, t in txns.items() if t["ref"]}
    entries = {key: t for key, t in txns.items() if not t["ref"]}
    deleted = {r["key"] for r in conn.execute("SELECT key FROM deleted_txns")}
    results = []
    for r in rows:
        if r["ts"] < start:
            results.append((r["txn_id"], "early", None))
            continue
        ref = (r["utr"].lstrip("0"), r["direction"]) if r["utr"] else None
        account = _resolve_account(re.sub(r"\D", "", r["instrument"] or ""), known_accounts, r["source"])
        if ref in by_ref:
            # A payment known only from an app is on some bank account; the statement says which.
            known = txns[by_ref[ref]]
            if known["account"].endswith(" UPI") and not account.endswith(" UPI"):
                known["account"] = account
            # A payment the user removed stays removed; it is only reported.
            results.append((r["txn_id"], "deleted" if by_ref[ref] in deleted else "known", by_ref[ref]))
            continue
        # Entries typed by hand, and alerts with no reference, have nothing to match on but amount and date.
        # Each one can only answer for one statement row.
        near = [
            (abs(t["ts"] - r["ts"]), t["account"] != account, key) for key, t in entries.items()
            if t["direction"] == r["direction"] and abs(t["amount"] - r["amount"]) < 0.01
            and abs(t["ts"] - r["ts"]) <= STATEMENT_MATCH_DAYS * 86400
        ]
        if near:
            key = min(near)[2]
            typed = entries.pop(key)["channel"] == "Manual"
            # The same payment can be on two statements; the second must find this entry too.
            if ref:
                by_ref[ref] = key
            results.append((r["txn_id"], "deleted" if key in deleted else "manual" if typed else "known", key))
            continue
        party = statements.payee_of(r["details"])
        hint = None
        if party in own:
            other = _resolve_account(re.sub(r"\D", "", party), known_accounts, r["source"])
            party = f"Transfer {'to' if r['direction'] == 'debit' else 'from'} {other}"
            hint = cat.SELF_TRANSFER
        key = f"{account}|{r['direction']}|{r['utr'] or r['txn_id']}"
        txns[key] = {
            "ts": r["ts"], "account": account, "direction": r["direction"], "amount": r["amount"], "payee": party,
            "info": r["details"], "ref": r["utr"] or None, "app": r["source"], "hint": hint, "from_statement": True,
            "channel": "Credit card" if " Card " in account else "Statement",
        }
        if ref:
            by_ref[ref] = key
        results.append((r["txn_id"], "deleted" if key in deleted else "added", key))
    conn.executemany("INSERT INTO statement_results VALUES(?, ?, ?)", results)


def build(conn) -> dict:
    migrate(conn)
    conn.executescript(REBUILT)
    owner = _owner_name(conn)
    decided = {r["key"]: (r["category"], r["subcategory"]) for r in conn.execute("SELECT * FROM txn_labels")}
    remembered = {
        r["payee_key"]: (r["category"], r["subcategory"]) for r in conn.execute("SELECT * FROM payee_labels")
    }

    bank, enrich, unparsed = [], [], Counter()
    start = datetime.strptime(db.get_state(conn, "start_date", "1970-01-02"), "%Y-%m-%d").timestamp()
    for e in conn.execute("SELECT * FROM emails WHERE internal_ts >= ? ORDER BY internal_ts", (start,)):
        rec = parse(e["sender"], e["subject"], e["body"])
        if rec is None:
            unparsed[(e["sender"], re.sub(r"\d[\d,.]*", "#", e["subject"] or ""))] += 1
            continue
        rec.update(email_id=e["id"], ts=e["internal_ts"])
        (bank if rec["role"] == "bank" else enrich).append(rec)

    txns = {}
    for r in bank:
        key = f"{r['account']}|{r['direction']}|{r['ref']}" if r["ref"] else f"mail|{r['email_id']}"
        txns.setdefault(key, {**r, "app": None, "hint": None})

    debits_by_ref = defaultdict(list)
    for t in txns.values():
        if t["ref"] and t["direction"] == "debit":
            debits_by_ref[t["ref"]].append(t)
    known_accounts = {t["account"] for t in txns.values()}

    merged = 0
    pot_names = set()
    for r in enrich:
        match = next(
            (t for t in debits_by_ref[r["ref"]] if abs(t["amount"] - r["amount"]) < 0.01), None
        )
        if match:
            merged += 1
            match["app"] = r["app"]
            match["hint"] = r["category_hint"]
            if r["app"] == "Jupiter":
                if cat.payee_key(match["payee"]) == "APSPL":
                    match["payee"] = f"{POT_PREFIX}{r['payee']}"
                    pot_names.add(r["payee"])
            else:
                match["payee"], match["info"] = r["payee"], r["info"]
            continue
        account = _resolve_account(r["account_hint"], known_accounts, r["app"])
        key = f"{account}|debit|{r['ref']}"
        if key not in txns:
            txns[key] = {**r, "account": account, "hint": r["category_hint"]}
            debits_by_ref[r["ref"]].append(txns[key])

    # A Jupiter payment whose bank alert is missing is still a pot deposit if that pot was seen before.
    for t in txns.values():
        if t.get("app") == "Jupiter" and t["payee"] in pot_names:
            t["payee"] = f"{POT_PREFIX}{t['payee']}"

    for m in conn.execute("SELECT * FROM manual_txns"):
        txns[f"manual|{m['id']}"] = {
            "ts": m["ts"], "account": m["account"], "direction": "debit", "amount": m["amount"],
            "payee": m["payee"], "info": "Added manually", "channel": "Manual",
            "ref": None, "app": None, "hint": None,
        }

    # Before pairing, so a transfer whose other side was missing is recognised as a self transfer.
    _fold_statement_rows(conn, txns, known_accounts, start)

    by_ref = defaultdict(list)
    for t in txns.values():
        if t["ref"]:
            by_ref[t["ref"]].append(t)
    paired = set()
    for ref, group in by_ref.items():
        if {t["direction"] for t in group} == {"debit", "credit"} and len({t["account"] for t in group}) > 1:
            paired.add(ref)

    # Balances follow the money that really moved: recorded before the user's deletions,
    # amount edits and account edits, which only shape the spending view.
    for key, t in txns.items():
        conn.execute(
            "INSERT INTO movements VALUES(?,?,?,?,?)", (key, t["ts"], t["account"], t["direction"], t["amount"])
        )
        if t.get("balance") is not None:
            conn.execute("INSERT INTO email_balances VALUES(?,?,?)", (t["account"], t["ts"], t["balance"]))
        # A pot deposit is spent from one account and arrives in Jupiter; it is a movement there, not a transaction.
        if t["direction"] == "debit" and t["payee"].startswith(POT_PREFIX):
            conn.execute("INSERT INTO movements VALUES(?,?,?,?,?)", (f"pot|{key}", t["ts"], POT_ACCOUNT, "credit", t["amount"]))

    notes = {r["key"]: r["note"] for r in conn.execute("SELECT * FROM notes")}
    deleted = {r["key"] for r in conn.execute("SELECT key FROM deleted_txns")}
    for key in deleted & txns.keys():
        del txns[key]

    edited = {r["key"]: r["amount"] for r in conn.execute("SELECT * FROM amount_overrides")}
    renamed = _renames(conn)
    known = category_groups(conn)
    overrides = {r["key"]: r for r in conn.execute("SELECT * FROM field_overrides")}
    for key, t in txns.items():
        counted = t["channel"] != "Credit card"
        subcategory = None
        if key in decided:
            (category, subcategory), status = decided[key], "approved"
        else:
            pk = cat.payee_key(t["payee"])
            if pk in remembered:
                category, subcategory = remembered[pk]
            elif t["ref"] in paired or _is_owner(t["payee"], owner):
                category = cat.SELF_TRANSFER
            elif t["hint"]:
                category = t["hint"]
            else:
                category = cat.by_rules(t["payee"], t["info"])
            category = renamed.get(category, category)
            # A keyword rule can still name a category that has since been deleted.
            if category not in known:
                category = cat.UNCATEGORISED
            if category == cat.UNCATEGORISED and t["direction"] == "credit":
                category = "Other income"
            # Every payment out waits for approval, as does anything recovered from a statement.
            # Other money received counts towards nothing.
            status = "pending" if t["direction"] == "debit" or t.get("from_statement") else "auto"
        # The user's own edits are applied last, so matching and suggestions still use the bank's values.
        ov = overrides.get(key)
        ts, payee, account = t["ts"], t["payee"], t["account"]
        if ov:
            payee, account = ov["payee"] or payee, ov["account"] or account
            if ov["date"]:
                ts = int(datetime.strptime(ov["date"], "%Y-%m-%d").replace(hour=12).timestamp())
        conn.execute(
            "INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                key, ts, datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                account, t["direction"], edited.get(key, t["amount"]), payee, t["info"],
                t["channel"], t["ref"], t["app"], category, subcategory, status,
                # Credit-card purchases are paid later through a card bill, which is what gets counted.
                int(counted),
                t["amount"] if key in edited else None,
                notes.get(key),
                t["payee"],
            ),
        )
    conn.commit()
    return {
        "transactions": len(txns),
        "merged_duplicates": merged,
        "self_transfer_pairs": len(paired),
        "unparsed": unparsed,
    }


def _clean_name(name) -> str:
    name = " ".join(str(name or "").split())
    if not 0 < len(name) <= 60:
        raise ValueError("name must be 1 to 60 characters")
    return name


def add_category(conn, name):
    name = _clean_name(name)
    conn.execute("INSERT OR IGNORE INTO categories(name, grp) VALUES(?, 'expense')", (name,))
    conn.execute("DELETE FROM deleted_categories WHERE name = ?", (name,))
    conn.commit()


def delete_category(conn, name):
    """Remove a spending category nothing uses. Built-in names stay gone when the ledger is rebuilt."""
    if category_groups(conn).get(name) != "expense" or name in PROTECTED:
        raise ValueError(f"{name} cannot be deleted")
    if conn.execute("SELECT 1 FROM transactions WHERE category = ?", (name,)).fetchone():
        raise ValueError(f"{name} still has transactions")
    if name in budget_categories(conn) or name in budgets(conn):
        raise ValueError(f"{name} is in use on the Budget page")
    for table, column in (
        ("categories", "name"), ("subcategories", "category"), ("txn_labels", "category"),
        ("payee_labels", "category"), ("budget_months", "category"), ("mandatory_categories", "category"),
    ):
        conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (name,))
    if name in cat.CATEGORIES:
        conn.execute("INSERT OR IGNORE INTO deleted_categories(name) VALUES(?)", (name,))
    conn.commit()


def add_subcategory(conn, category, name):
    if category not in category_groups(conn):
        raise ValueError(f"unknown category: {category}")
    conn.execute(
        "INSERT OR IGNORE INTO subcategories(category, name) VALUES(?, ?)", (category, _clean_name(name))
    )
    conn.commit()


def rename_category(conn, old, new):
    new = _clean_name(new)
    groups = category_groups(conn)
    if old not in groups:
        raise ValueError(f"unknown category: {old}")
    if old in PROTECTED or groups[old] == "income":
        raise ValueError(f"{old} cannot be renamed")
    if new == old:
        return
    if new in groups:
        # Merging: the target keeps its own subcategories and gains the old one's.
        conn.execute("UPDATE OR IGNORE subcategories SET category = ? WHERE category = ?", (new, old))
        conn.execute("DELETE FROM subcategories WHERE category = ?", (old,))
        conn.execute("DELETE FROM categories WHERE name = ?", (old,))
    else:
        conn.execute("UPDATE categories SET name = ? WHERE name = ?", (new, old))
        conn.execute("UPDATE subcategories SET category = ? WHERE category = ?", (new, old))
    for table in ("txn_labels", "payee_labels"):
        conn.execute(f"UPDATE {table} SET category = ? WHERE category = ?", (new, old))
    # The budget follows the category; a merge keeps the target's own budget.
    conn.execute("UPDATE OR IGNORE budgets SET category = ? WHERE category = ?", (new, old))
    conn.execute("DELETE FROM budgets WHERE category = ?", (old,))
    conn.execute("UPDATE OR IGNORE budget_months SET category = ? WHERE category = ?", (new, old))
    conn.execute("DELETE FROM budget_months WHERE category = ?", (old,))
    conn.execute("UPDATE OR IGNORE mandatory_categories SET category = ? WHERE category = ?", (new, old))
    conn.execute("DELETE FROM mandatory_categories WHERE category = ?", (old,))
    conn.execute("UPDATE OR IGNORE budget_categories SET category = ? WHERE category = ?", (new, old))
    conn.execute("DELETE FROM budget_categories WHERE category = ?", (old,))
    # Built-in names are remembered so the keyword rules keep suggesting the renamed category.
    conn.execute("UPDATE category_renames SET new = ? WHERE new = ?", (new, old))
    conn.execute("DELETE FROM category_renames WHERE old = ?", (new,))
    if old in cat.CATEGORIES:
        conn.execute("INSERT OR REPLACE INTO category_renames(old, new) VALUES(?, ?)", (old, new))
    conn.commit()


def rename_subcategory(conn, category, old, new):
    new = _clean_name(new)
    if old not in subcategories(conn).get(category, []):
        raise ValueError(f"unknown subcategory: {old}")
    if new == old:
        return
    # Renaming onto an existing name merges the two.
    if new in subcategories(conn)[category]:
        conn.execute("DELETE FROM subcategories WHERE category = ? AND name = ?", (category, old))
    else:
        conn.execute("UPDATE subcategories SET name = ? WHERE category = ? AND name = ?", (new, category, old))
    for table in ("txn_labels", "payee_labels"):
        conn.execute(
            f"UPDATE {table} SET subcategory = ? WHERE category = ? AND subcategory = ?", (new, category, old)
        )
    conn.commit()


def decide(conn, items):
    """Approve transactions with the given category, and remember it for the payee's next payment."""
    groups, subs = category_groups(conn), subcategories(conn)
    for item in items:
        key, category, sub = item["key"], item["category"], item.get("subcategory") or None
        if category not in groups:
            raise ValueError(f"unknown category: {category}")
        if sub and sub not in subs.get(category, []):
            raise ValueError(f"unknown subcategory: {sub}")
        row = conn.execute("SELECT bank_payee AS payee FROM transactions WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise ValueError("unknown transaction")
        conn.execute(
            "INSERT INTO txn_labels(key, category, subcategory) VALUES(?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET category = excluded.category, subcategory = excluded.subcategory",
            (key, category, sub),
        )
        conn.execute(
            "INSERT INTO payee_labels(payee_key, category, subcategory) VALUES(?, ?, ?) "
            "ON CONFLICT(payee_key) DO UPDATE SET category = excluded.category, subcategory = excluded.subcategory",
            (cat.payee_key(row["payee"]), category, sub),
        )
    conn.commit()


def delete(conn, key):
    """Hide a transaction for good; it stays hidden when the ledger is rebuilt from emails."""
    row = conn.execute("SELECT date, payee, amount FROM transactions WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise ValueError("unknown transaction")
    if key.startswith("manual|"):
        conn.execute("DELETE FROM manual_txns WHERE id = ?", (int(key.split("|")[1]),))
        for table in ("txn_labels", "notes", "amount_overrides", "field_overrides"):
            conn.execute(f"DELETE FROM {table} WHERE key = ?", (key,))
    else:
        conn.execute(
            "INSERT OR IGNORE INTO deleted_txns(key, summary) VALUES(?, ?)",
            (key, f"{row['date']} {row['payee']} {row['amount']}"),
        )
    conn.commit()


def set_amount(conn, key, amount):
    """Override a transaction's amount; None restores the amount from the bank alert."""
    if conn.execute("SELECT 1 FROM transactions WHERE key = ?", (key,)).fetchone() is None:
        raise ValueError("unknown transaction")
    if amount is None:
        conn.execute("DELETE FROM amount_overrides WHERE key = ?", (key,))
    else:
        amount = float(amount)
        if not 0 <= amount < 1e9:
            raise ValueError("amount must be zero or more")
        conn.execute(
            "INSERT INTO amount_overrides(key, amount) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET amount = excluded.amount",
            (key, round(amount, 2)),
        )
    conn.commit()


def _clean_note(note) -> str:
    note = " ".join(str(note or "").split())
    if len(note) > 200:
        raise ValueError("description must be 200 characters or fewer")
    return note


def budgets(conn) -> dict:
    """Default monthly budget per spending category, in rupees."""
    return {r["category"]: r["amount"] for r in conn.execute("SELECT category, amount FROM budgets")}


def budget_months(conn) -> dict:
    """Budgets set for one month, which replace the default: {month: {category: amount}}. Zero means no budget."""
    out = defaultdict(dict)
    for r in conn.execute("SELECT month, category, amount FROM budget_months"):
        out[r["month"]][r["category"]] = r["amount"]
    return dict(out)


def budget_categories(conn) -> list:
    """Categories added on the Budget page, shown there every month even with nothing spent."""
    return [r["category"] for r in conn.execute("SELECT category FROM budget_categories ORDER BY category")]


def add_budget_category(conn, name):
    name = _clean_name(name)
    if category_groups(conn).get(name, "expense") != "expense":
        raise ValueError("budgets are for spending categories")
    add_category(conn, name)
    conn.execute("INSERT OR IGNORE INTO budget_categories(category) VALUES(?)", (name,))
    conn.commit()


def remove_budget_category(conn, name):
    """Take a category off the Budget page's permanent list. The category itself stays."""
    conn.execute("DELETE FROM budget_categories WHERE category = ?", (name,))
    conn.commit()


def _budget_amount(amount):
    value = None if amount in (None, "") else round(float(amount), 2)
    if value is not None and not 0 <= value < 1e9:
        raise ValueError("budget must be zero or more")
    return value


def set_budget(conn, category, amount, month=None):
    """Set a category's default budget, or with a month that month's budget. Empty removes it."""
    if category_groups(conn).get(category) != "expense":
        raise ValueError("budgets are for spending categories")
    value = _budget_amount(amount)
    if month:
        month = datetime.strptime(month, "%Y-%m").strftime("%Y-%m")
        if value is None:
            conn.execute("DELETE FROM budget_months WHERE month = ? AND category = ?", (month, category))
        else:
            conn.execute(
                "INSERT INTO budget_months(month, category, amount) VALUES(?, ?, ?) "
                "ON CONFLICT(month, category) DO UPDATE SET amount = excluded.amount",
                (month, category, value),
            )
        conn.commit()
        return
    # Months already over keep the budget they had, so changing a default does not rewrite history.
    old = budgets(conn).get(category, 0)
    conn.execute(
        "INSERT OR IGNORE INTO budget_months(month, category, amount) "
        "SELECT DISTINCT substr(date, 1, 7), ?, ? FROM transactions WHERE substr(date, 1, 7) < ?",
        (category, old, datetime.now().strftime("%Y-%m")),
    )
    if value:
        conn.execute(
            "INSERT INTO budgets(category, amount) VALUES(?, ?) ON CONFLICT(category) DO UPDATE SET amount = excluded.amount",
            (category, value),
        )
    else:
        conn.execute("DELETE FROM budgets WHERE category = ?", (category,))
    conn.commit()


def mandatory_categories(conn) -> list:
    """Spending categories that must be paid (rent, EMIs, bills); the rest are normal."""
    return [r["category"] for r in conn.execute("SELECT category FROM mandatory_categories ORDER BY category")]


def set_mandatory(conn, category, mandatory):
    if category_groups(conn).get(category) != "expense":
        raise ValueError("only spending categories can be marked mandatory")
    if mandatory:
        conn.execute("INSERT OR IGNORE INTO mandatory_categories(category) VALUES(?)", (category,))
    else:
        conn.execute("DELETE FROM mandatory_categories WHERE category = ?", (category,))
    conn.commit()


def set_note(conn, key, note):
    if conn.execute("SELECT 1 FROM transactions WHERE key = ?", (key,)).fetchone() is None:
        raise ValueError("unknown transaction")
    note = _clean_note(note)
    if note:
        conn.execute(
            "INSERT INTO notes(key, note) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET note = excluded.note",
            (key, note),
        )
    else:
        conn.execute("DELETE FROM notes WHERE key = ?", (key,))
    conn.commit()


def add_expense(conn, item):
    """Record a payment that has no bank alert, such as cash. It is approved as entered."""
    day = datetime.strptime(item["date"], "%Y-%m-%d")
    amount = float(item["amount"])
    if not 0 < amount < 1e9:
        raise ValueError("amount must be more than zero")
    payee, account = _clean_name(item["payee"]), _clean_name(item.get("account") or "Cash")
    category, sub = item["category"], item.get("subcategory") or None
    if category not in category_groups(conn):
        raise ValueError(f"unknown category: {category}")
    if sub and sub not in subcategories(conn).get(category, []):
        raise ValueError(f"unknown subcategory: {sub}")
    note = _clean_note(item.get("note"))
    cur = conn.execute(
        "INSERT INTO manual_txns(ts, amount, payee, account) VALUES(?, ?, ?, ?)",
        (int(day.replace(hour=12).timestamp()), round(amount, 2), payee, account),
    )
    key = f"manual|{cur.lastrowid}"
    conn.execute("INSERT INTO txn_labels(key, category, subcategory) VALUES(?, ?, ?)", (key, category, sub))
    if note:
        conn.execute("INSERT INTO notes(key, note) VALUES(?, ?)", (key, note))
    conn.commit()


def edit(conn, item):
    """Apply every field of the edit popup to one transaction."""
    key = item["key"]
    row = conn.execute("SELECT * FROM transactions WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise ValueError("unknown transaction")
    amount = float(item["amount"])
    bank_amount = row["amount"] if row["original_amount"] is None else row["original_amount"]
    set_amount(conn, key, None if abs(amount - bank_amount) < 0.005 else amount)
    day = datetime.strptime(item["date"], "%Y-%m-%d").strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO field_overrides(key, payee, date, account) VALUES(?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET payee = excluded.payee, date = excluded.date, account = excluded.account",
        (key, _clean_name(item["payee"]), day, _clean_name(item["account"])),
    )
    conn.commit()
    set_note(conn, key, item.get("note"))
    category = item["category"]
    # A payment still waiting for review stays there until it is given a real category.
    if not (row["status"] == "pending" and category == cat.UNCATEGORISED):
        decide(conn, [{"key": key, "category": category, "subcategory": item.get("subcategory")}])


def _is_bank_account(account: str) -> bool:
    # Cards and UPI receipts with no known account have no balance to track.
    return not re.search(r"\bCard\b|\bUPI$", account)


def balances(conn) -> list:
    """Estimated balance per bank account: the last known figure plus everything alerted since."""
    accounts = {r["account"] for r in conn.execute("SELECT DISTINCT account FROM movements")}
    accounts |= {r["account"] for r in conn.execute("SELECT DISTINCT account FROM balance_anchors")}
    excluded = {r["account"] for r in conn.execute("SELECT account FROM balance_excluded")}
    out = []
    for account in sorted(a for a in accounts if _is_bank_account(a)):
        manual = conn.execute(
            "SELECT ts, amount FROM balance_anchors WHERE account = ? ORDER BY ts DESC, id DESC LIMIT 1", (account,)
        ).fetchone()
        email = conn.execute(
            "SELECT ts, amount FROM email_balances WHERE account = ? ORDER BY ts DESC LIMIT 1", (account,)
        ).fetchone()
        known = [(r["ts"], r["amount"], source) for r, source in ((manual, "you"), (email, "alert")) if r]
        if not known:
            out.append({"account": account, "balance": None, "in_total": account not in excluded})
            continue
        ts, amount, source = max(known)
        since = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(CASE direction WHEN 'credit' THEN amount ELSE -amount END), 0) AS net "
            # An expense entered ahead of its date has not left the account yet.
            "FROM movements WHERE account = ? AND ts > ? AND ts <= ?",
            (account, ts, int(datetime.now().timestamp())),
        ).fetchone()
        out.append({
            "account": account, "balance": round(amount + since["net"], 2), "confirmed": amount,
            "confirmed_ts": ts, "source": source, "since": since["n"], "in_total": account not in excluded,
        })
    return out


def set_balance(conn, account, amount):
    """Record the true balance the user read from their bank, as of now."""
    known = {r["account"] for r in conn.execute("SELECT DISTINCT account FROM movements")}
    if account not in known or not _is_bank_account(account):
        raise ValueError(f"unknown account: {account}")
    amount = float(amount)
    if not -1e10 < amount < 1e10:
        raise ValueError("balance is out of range")
    conn.execute(
        "INSERT INTO balance_anchors(account, ts, amount) VALUES(?, ?, ?)",
        (account, int(datetime.now().timestamp()), round(amount, 2)),
    )
    conn.commit()


def set_balance_in_total(conn, account, include):
    """Choose whether an account's balance counts towards the total."""
    if include:
        conn.execute("DELETE FROM balance_excluded WHERE account = ?", (account,))
    else:
        conn.execute("INSERT OR IGNORE INTO balance_excluded(account) VALUES(?)", (str(account),))
    conn.commit()
