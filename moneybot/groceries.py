"""Grocery bills and the Grocery tab's figures. Bills only describe payments already in the ledger: they add no spending.

Star Bazaar invoices are links, emailed by the user to themselves. The page carries the whole bill as data.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime

from . import categories as cat
from . import ledger

STAR_HOST = "starbazaar.karnival.com"
STAR_LINK = re.compile(rf"https://{re.escape(STAR_HOST)}/q/zd/[A-Za-z0-9]+/?(?:\?ch=\d+)?")
MAX_PAGE = 3_000_000
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"

STAR_PAYEE = re.compile(r"STAR\s*(BAZAAR|MARKET)")
GROUPS = ["Fruit", "Vegetables", "Leaves and herbs", "Dairy", "Meat and eggs", "Staples", "Snacks and packaged",
          "Household", "Carry bags", "Other"]
GROUP_RULES = [
    ("Carry bags", r"CARRY BAG"),
    ("Leaves and herbs", r"CORIANDER|METHI|SPINACH|MINT|CURRY LEAVES|BACHALI|PALAK|GONGURA|AMARANTH|DILL"),
    ("Fruit", r"GUAVA|PAPAYA|BANANA|APPLE|MANGO|MUSKMELON|DRGFRU|ORANGE|GRAPE|POMEGRAN|WATERMELON|PINEAPPLE|GOOSEBERRY|LEMON|SAPOTA|PEAR\b"),
    ("Dairy", r"MILK|CURD|PANEER|BUTTER|GHEE|CHEESE"),
    ("Meat and eggs", r"CHICKEN|\bEGG|MUTTON|FISH"),
    ("Staples", r"RICE|ATTA|DAL\b|FLOUR|\bOIL\b|SALT|SUGAR|GROUNDNUT|TOOR|MOONG"),
    ("Snacks and packaged", r"MCCAIN|BISCUIT|CHIPS|NOODLE|CHOCO|JUICE"),
    ("Household", r"SOAP|DETERGENT|TISSUE|CLEANER|SHAMPOO"),
    ("Vegetables", r"TOMATO|ONION|POTATO|CARROT|BRINJ|CUCU|RADISH|GOURD|DRUMSTICK|CHILLI|BEANS|CABBAGE|CAULI|OKRA|LADY"),
]
GROUP_RULES = [(name, re.compile(pattern)) for name, pattern in GROUP_RULES]


def group_of(name: str) -> str:
    key = cat.payee_key(name)
    return next((group for group, rule in GROUP_RULES if rule.search(key)), "Other")


def nice_name(description: str) -> str:
    """'GUAVA JMB PNK KG' -> 'Guava Jmb Pnk'"""
    return re.sub(r"\s+(KG|PC|P)$", "", " ".join(description.split()), flags=re.I).title()


def parse_star(page: str) -> dict:
    """A bill page -> bill. Raises ValueError unless the items add up to the amount paid."""
    blocks = re.findall(r'<script[^>]*type="?qwik/json"?[^>]*>(.*?)</script>', page, re.S)
    if not blocks:
        raise ValueError("the bill page has changed")
    try:
        objs = json.loads(max(blocks, key=len).replace("\\x3C", "<"))["objs"]

        def at(ref):
            return objs[int(ref.rstrip("!"), 36)]

        bill = next(o for o in objs if isinstance(o, dict) and {"items", "billInfo", "paymentInfo"} <= o.keys())
        info = {k: at(v) for k, v in at(bill["billInfo"]).items()}
        paid = float(at(at(bill["paymentInfo"])["paidAmount"]))
        rows = [{k: at(v) for k, v in at(ref).items()} for ref in at(bill["items"])]
        items = []
        for line, r in enumerate(rows):
            if r.get("voidItem"):
                continue
            unit = (r.get("productName") or "").split()[-1:] or [""]
            items.append({
                "line": line, "code": str(r["code"]), "name": nice_name(r["description"]), "unit": unit[0].upper(),
                "quantity": float(r["quantity"]), "price": float(r["sellingPrice"]),
                "mrp": float(r["mrp"]) if r.get("mrp") else None, "amount": float(r["amount"]),
            })
        moment = datetime.strptime(f"{info['purchaseDate']}{info['purchaseTime']}", "%Y%m%d%H%M%S")
    except (KeyError, IndexError, TypeError, ValueError, StopIteration, AttributeError):
        raise ValueError("the bill page has changed") from None
    if info.get("billType") != "Billing":
        raise ValueError(f"this is a {info.get('billType')} bill, not a purchase")
    if not items or abs(sum(i["amount"] for i in items) - paid) > 0.05:
        raise ValueError("the items do not add up to the amount paid")
    return {"id": f"star:{info['billNumber']}", "ts": int(moment.timestamp()), "total": paid, "items": items}


def store(conn, bill, source="Star Bazaar"):
    conn.execute("INSERT OR REPLACE INTO bills(id, source, ts, total) VALUES(?, ?, ?, ?)",
                 (bill["id"], source, bill["ts"], bill["total"]))
    conn.execute("DELETE FROM bill_items WHERE bill_id = ?", (bill["id"],))
    conn.executemany(
        "INSERT INTO bill_items(bill_id, line, code, name, unit, quantity, price, mrp, amount) "
        "VALUES(:bill_id, :line, :code, :name, :unit, :quantity, :price, :mrp, :amount)",
        [{**i, "bill_id": bill["id"]} for i in bill["items"]],
    )


def _download(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if urllib.parse.urlsplit(response.geturl()).hostname != STAR_HOST:
                raise ValueError("the link went to another website")
            return response.read(MAX_PAGE).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError(f"the link could not be opened ({exc})") from None


def fetch_links(conn, text: str, email_id: str, received_ts: int, download=_download) -> int:
    """Read every bill link in an email's text that has not been read yet. Failures are kept and tried again."""
    done = {r["url"] for r in conn.execute("SELECT url FROM bill_links WHERE error IS NULL")}
    found = 0
    for url in dict.fromkeys(STAR_LINK.findall(text)):
        if url in done:
            continue
        bill_id, error = None, None
        try:
            bill = parse_star(download(url))
            store(conn, bill)
            bill_id = bill["id"]
            found += 1
        except ValueError as exc:
            error = str(exc)
        conn.execute("INSERT OR REPLACE INTO bill_links(url, email_id, received_ts, bill_id, error) VALUES(?, ?, ?, ?, ?)",
                     (url, email_id, received_ts, bill_id, error))
    conn.commit()
    return found


def set_group(conn, code, group):
    if group not in GROUPS:
        raise ValueError("unknown group")
    conn.execute("INSERT INTO item_groups(code, grp) VALUES(?, ?) ON CONFLICT(code) DO UPDATE SET grp = excluded.grp",
                 (str(code), group))
    conn.commit()


def _match_bills(conn, bills) -> dict:
    """Each bill to its payment: the same amount within two days, preferring a payment to the shop."""
    payments = conn.execute(
        "SELECT key, ts, amount, payee, bank_payee FROM transactions WHERE direction = 'debit'"
    ).fetchall()
    used, matched = set(), {}
    for b in sorted(bills, key=lambda b: b["ts"]):
        near = [
            (not STAR_PAYEE.search(cat.payee_key(p["bank_payee"] or p["payee"])), abs(p["ts"] - b["ts"]), p["key"]) for p in payments
            if p["key"] not in used and abs(p["amount"] - b["total"]) < 0.01 and abs(p["ts"] - b["ts"]) <= 2 * 86400
        ]
        if near:
            matched[b["id"]] = min(near)[2]
            used.add(matched[b["id"]])
    return matched


def summary(conn) -> dict:
    """Everything the Grocery tab shows, so the dashboard and the phone agree."""
    groceries = ledger._renames(conn).get("Groceries", "Groceries")
    groups = {r["code"]: r["grp"] for r in conn.execute("SELECT * FROM item_groups")}
    months = defaultdict(lambda: {
        "total": 0.0, "billed": 0.0, "subs": {}, "groups": defaultdict(float),
        "items": {}, "bills": [],
    })
    for t in conn.execute(
        "SELECT date, amount, payee, subcategory FROM transactions WHERE category = ? AND direction = 'debit' "
        "AND counted = 1 AND status != 'pending'", (groceries,)
    ):
        m = months[t["date"][:7]]
        m["total"] += t["amount"]
        name = t["subcategory"] or "No subcategory"
        row = m["subs"].setdefault(name, {"name": name, "amount": 0.0, "payees": set()})
        row["amount"] += t["amount"]
        row["payees"].add(t["payee"])

    bills = [dict(b) for b in conn.execute("SELECT * FROM bills ORDER BY ts")]
    matched = _match_bills(conn, bills)
    history = defaultdict(list)
    for b in bills:
        day = datetime.fromtimestamp(b["ts"]).strftime("%Y-%m-%d")
        m = months[day[:7]]
        m["billed"] += b["total"]
        lines = conn.execute("SELECT * FROM bill_items WHERE bill_id = ? ORDER BY line", (b["id"],)).fetchall()
        m["bills"].append({
            "id": b["id"], "source": b["source"], "date": day, "total": b["total"], "matched": b["id"] in matched,
            "items": [{"name": i["name"], "quantity": i["quantity"], "unit": i["unit"], "price": i["price"],
                       "amount": i["amount"]} for i in lines],
        })
        for i in lines:
            group = groups.get(i["code"]) or group_of(i["name"])
            m["groups"][group] += i["amount"]
            history[i["code"]].append({"date": day, "price": i["price"]})
            row = m["items"].setdefault(i["code"], {
                "code": i["code"], "name": i["name"], "unit": i["unit"], "group": group, "quantity": 0.0, "amount": 0.0,
            })
            row.update(name=i["name"], price=i["price"])
            row["quantity"] = round(row["quantity"] + i["quantity"], 3)
            row["amount"] = round(row["amount"] + i["amount"], 2)

    out = {}
    for month, m in months.items():
        items = sorted(m["items"].values(), key=lambda i: -i["amount"])
        for item in items:
            item["history"] = [h for h in history[item["code"]] if h["date"][:7] <= month][-8:]
        out[month] = {
            "total": round(m["total"], 2), "billed": round(m["billed"], 2),
            "subcategories": sorted(
                ({"name": r["name"], "amount": round(r["amount"], 2), "payees": sorted(r["payees"])} for r in m["subs"].values()),
                key=lambda r: -r["amount"],
            ),
            "groups": sorted(({"name": g, "amount": round(a, 2)} for g, a in m["groups"].items()), key=lambda g: -g["amount"]),
            "items": items, "bills": list(reversed(m["bills"])),
        }
    problems = [{"message": f"Could not read a bill: {r['error']}", "url": r["url"]}
                for r in conn.execute("SELECT url, error FROM bill_links WHERE error IS NOT NULL")]
    problems += [{"message": f"No matching payment for the {b['source']} bill of ₹{b['total']:.2f} on "
                             f"{datetime.fromtimestamp(b['ts']):%d %b}", "url": None}
                 for b in bills if b["id"] not in matched]
    return {"months": out, "problems": problems, "groups": GROUPS}
