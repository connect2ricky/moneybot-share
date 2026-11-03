import sqlite3

from .config import DB_FILE

SCHEMA = """
CREATE TABLE IF NOT EXISTS bills (
    id     TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    ts     INTEGER NOT NULL,
    total  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS bill_items (
    bill_id  TEXT NOT NULL,
    line     INTEGER NOT NULL,
    code     TEXT NOT NULL,
    name     TEXT NOT NULL,
    unit     TEXT,
    quantity REAL NOT NULL,
    price    REAL NOT NULL,
    mrp      REAL,
    amount   REAL NOT NULL,
    PRIMARY KEY (bill_id, line)
);
CREATE TABLE IF NOT EXISTS bill_links (
    url         TEXT PRIMARY KEY,
    email_id    TEXT NOT NULL,
    received_ts INTEGER NOT NULL,
    bill_id     TEXT,
    error       TEXT
);
CREATE TABLE IF NOT EXISTS item_groups (
    code TEXT PRIMARY KEY,
    grp  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS budget_months (
    month    TEXT NOT NULL,
    category TEXT NOT NULL,
    amount   REAL NOT NULL,
    PRIMARY KEY (month, category)
);
CREATE TABLE IF NOT EXISTS statement_files (
    email_id    TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    filename    TEXT,
    received_ts INTEGER NOT NULL,
    period      TEXT,
    row_count   INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    seen        INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS statement_rows (
    txn_id     TEXT PRIMARY KEY,
    email_id   TEXT NOT NULL,
    source     TEXT NOT NULL,
    ts         INTEGER NOT NULL,
    direction  TEXT NOT NULL,
    amount     REAL NOT NULL,
    details    TEXT NOT NULL,
    utr        TEXT,
    instrument TEXT
);
CREATE TABLE IF NOT EXISTS mandatory_categories (
    category TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS budgets (
    category TEXT PRIMARY KEY,
    amount   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS card_statements (
    email_id       TEXT PRIMARY KEY,
    card           TEXT NOT NULL,
    received_ts    INTEGER NOT NULL,
    last4          TEXT,
    period_start   TEXT,
    period_end     TEXT,
    statement_date TEXT,
    due_date       TEXT,
    total_due      REAL,
    min_due        REAL,
    previous       REAL,
    credit_limit   REAL,
    available      REAL,
    balanced       INTEGER,
    skipped        INTEGER NOT NULL DEFAULT 0,
    error          TEXT
);
CREATE TABLE IF NOT EXISTS card_rows (
    email_id TEXT NOT NULL,
    seq      INTEGER NOT NULL,
    date     TEXT NOT NULL,
    details  TEXT NOT NULL,
    amount   REAL NOT NULL,
    credit   INTEGER NOT NULL,
    PRIMARY KEY (email_id, seq)
);
CREATE TABLE IF NOT EXISTS card_loans (
    email_id TEXT NOT NULL,
    loan     TEXT NOT NULL,
    tenure   INTEGER NOT NULL,
    PRIMARY KEY (email_id, loan)
);
CREATE TABLE IF NOT EXISTS budget_categories (
    category TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS deleted_categories (
    name TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS emails (
    id          TEXT PRIMARY KEY,
    thread_id   TEXT,
    sender      TEXT NOT NULL,
    subject     TEXT,
    internal_ts INTEGER NOT NULL,
    snippet     TEXT,
    body        TEXT
);
CREATE INDEX IF NOT EXISTS emails_sender ON emails(sender);
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def get_state(conn, key, default=None):
    row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_state(conn, key, value):
    conn.execute(
        "INSERT INTO state(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
