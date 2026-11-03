"""Turn stored alert emails into records.

role "bank"   -> an account movement reported by the bank itself (source of truth)
role "enrich" -> a UPI app's receipt for a payment the bank also reports
"""
import re

AMOUNT = r"([\d,]+(?:\.\d+)?)"


def _amt(text: str) -> float:
    return float(text.replace(",", ""))


def _acct(bank: str, digits: str) -> str:
    return f"{bank} {re.sub(r'[^0-9]', '', digits)}"


def _split_axis_info(info: str) -> dict:
    m = re.match(r"UPI/(P2A|P2M)/(\d+)/([^/]+)(?:/([^/]*)/(.*))?", info)
    if m:
        return {"channel": "UPI", "ref": m.group(2), "payee": m.group(3).strip()}
    return {"channel": "Bank", "ref": None, "payee": re.sub(r"\d{9,}", "", info).strip(" /_-")}


def axis(subject, body):
    m = re.search(
        rf"Amount (Debited|Credited):\s*INR {AMOUNT}\s*Account Number:\s*(XX\d+).*?"
        r"Transaction Info:\s*(.+)",
        body,
        re.S,
    )
    if m:
        direction, amount, acct, info = m.group(1), m.group(2), m.group(3), m.group(4)
        info = info.splitlines()[0].strip()
    else:
        m = re.search(
            rf"A/c no\. (XX\d+) has been (debited|credited) with INR {AMOUNT} on .*? IST by (.+?)\. ",
            body,
        )
        if not m:
            return None
        acct, direction, amount, info = m.groups()
    return {
        "role": "bank",
        "account": _acct("Axis", acct),
        "direction": direction.lower()[:-2],
        "amount": _amt(amount),
        "info": info,
        **_split_axis_info(info),
    }


def hdfc(subject, body):
    m = re.search(
        rf"Rs\.? ?{AMOUNT} is debited from your account ending (\d+) towards VPA (\S+) \((.*?)\)",
        body,
    )
    if m:
        ref = re.search(r"reference no\.: *(\d+)", body)
        return {
            "role": "bank", "account": _acct("HDFC", m.group(2)), "direction": "debit",
            "amount": _amt(m.group(1)), "payee": m.group(4).strip() or m.group(3),
            "info": f"UPI to {m.group(3)}", "channel": "UPI", "ref": ref and ref.group(1),
        }
    m = re.search(
        rf"Rs\.? ?{AMOUNT} has been successfully credited to your HDFC Bank account ending in (\d+)",
        body,
    )
    if m:
        sender = re.search(r"Sender: (.+?)(?: \(VPA: (\S+?)\))?\n", body)
        ref = re.search(r"UPI Reference No\.: *(\d+)", body)
        return {
            "role": "bank", "account": _acct("HDFC", m.group(2)), "direction": "credit",
            "amount": _amt(m.group(1)), "payee": sender.group(1).strip() if sender else "",
            "info": f"UPI from {sender.group(2)}" if sender and sender.group(2) else "Credit",
            "channel": "UPI", "ref": ref and ref.group(1),
        }
    m = re.search(
        rf"Rs\.? ?{AMOUNT} has been debited from your HDFC Bank Credit Card ending (\d+) towards (.+?) on ",
        body,
    )
    if m:
        return {
            "role": "bank", "account": _acct("HDFC Card", m.group(2)), "direction": "debit",
            "amount": _amt(m.group(1)), "payee": m.group(3).strip(), "info": "Credit card purchase",
            "channel": "Credit card", "ref": None,
        }
    return None


def icici(subject, body):
    m = re.search(
        rf"A purchase of Rs\.? ?{AMOUNT} has been made using your Debit Card linked to "
        r"ICICI Bank Account (XX\d+) on \S+\. Info: (.+?) ?\.",
        body,
    )
    if m:
        after = re.search(rf"Available Balance in your account is Rs\.? ?{AMOUNT}", body)
        return {
            "role": "bank", "account": _acct("ICICI", m.group(2)), "direction": "debit",
            "amount": _amt(m.group(1)), "payee": m.group(3).strip(), "info": "Debit card purchase",
            "channel": "Debit card", "ref": None,
            # The only alert that states the balance left after the transaction.
            "balance": _amt(after.group(1)) if after else None,
        }
    m = re.search(
        rf"ICICI Bank Account (XX\d+) has been (credited|debited) with INR {AMOUNT} on \S+\. "
        r"Info: (.+?)\.\n",
        body,
    )
    if m:
        return {
            "role": "bank", "account": _acct("ICICI", m.group(1)),
            "direction": m.group(2)[:-2], "amount": _amt(m.group(3)),
            "payee": m.group(4).strip(), "info": m.group(4).strip(), "channel": "Bank", "ref": None,
        }
    return None


def jupiter(subject, body):
    m = re.search(rf"You paid\s*₹ ?{AMOUNT}\s*Paid to\s*(.+)", body)
    # Jupiter sometimes masks the bank reference; its own transaction ID still keeps the record unique.
    ref = re.search(r"Bank reference Number\s*(\d+)", body) or re.search(r"Transaction ID\s*(\d+)", body)
    if not (m and ref):
        return None
    return {
        "role": "enrich", "app": "Jupiter", "account_hint": "", "direction": "debit",
        "amount": _amt(m.group(1)), "payee": m.group(2).strip(), "ref": ref.group(1),
        "channel": "UPI", "info": "Jupiter UPI payment", "category_hint": None,
    }


PHONEPE_CATEGORIES = {
    "mobile": "Mobile & Internet",
    "broadband/landline": "Mobile & Internet",
    "electricity": "Bills & Utilities",
    "lpg cylinder": "Bills & Utilities",
}


def phonepe(subject, body):
    flat = " ".join(body.split())
    m = re.search(rf"Payment For \S+ ₹ ?{AMOUNT} Txn", flat)
    ref = re.search(r"Bank Ref\. No\. : (\d+)", flat)
    if not (m and ref) or "Txn. status : Successful" not in flat:
        return None
    acct = re.search(r"Debited from (?:Bank )?Account :? ?(X+\d+)", flat)
    cat = re.search(r"Category : (.+?) Provider : (.+?) Hi ", flat)
    return {
        "role": "enrich", "app": "PhonePe", "direction": "debit",
        "account_hint": re.sub(r"\D", "", acct.group(1)) if acct else "",
        "amount": _amt(m.group(1)), "ref": ref.group(1), "channel": "UPI",
        "payee": cat.group(2).strip() if cat else "PhonePe bill payment",
        "info": f"PhonePe {cat.group(1).strip()}" if cat else "PhonePe bill payment",
        "category_hint": PHONEPE_CATEGORIES.get(cat.group(1).strip().lower()) if cat else None,
    }


PARSERS = [
    ("alerts@axis.bank.in", axis),
    ("alerts@hdfcbank.bank.in", hdfc),
    ("alert@icici.bank.in", icici),
    ("customernotification@icici.bank.in", icici),
    ("noreply@jupiter.money", jupiter),
    ("noreply@phonepe.com", phonepe),
]


def parse(sender, subject, body):
    for address, fn in PARSERS:
        if sender == address:
            return fn(subject or "", body or "")
    return None
