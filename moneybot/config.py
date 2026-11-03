from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = ROOT / "credentials.json"
TOKEN_FILE = ROOT / "token.json"
DATA_DIR = ROOT / "data"
DB_FILE = DATA_DIR / "moneybot.db"

# Encrypted backups: a clone of a separate private repository, inside the ignored data folder.
BACKUP_DIR = ROOT / "data" / "backups"
# Optional: set both to use `moneybot backup` and the phone app. See README.md, "Backups and the phone app".
BACKUP_REPO = ""  # for example "your-github-user/moneybot-data"; create it as a PRIVATE repository
BACKUP_GH_USER = ""  # your GitHub user name

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Matched against the From address; edit after running `moneybot discover`.
SENDER_DOMAINS = [
    "axisbank.com",
    "axis.bank.in",
    "icicibank.com",
    "icici.bank.in",
    "hdfcbank.net",
    "hdfcbank.com",
    "hdfc.bank.in",
    "hdfcbank.bank.in",
    "jupiter.money",
    "indusind.com",
    "rbl.bank.in",
    "phonepe.com",
]

# Statements the user asks for, found by Gmail search: source name -> (exact sender, query, file type).
STATEMENT_SOURCES = {
    "PhonePe": ("noreply@phonepe.com", 'from:noreply@phonepe.com subject:"transaction statement" has:attachment', ".csv"),
    "ICICI": ("customernotification@icici.bank.in", 'from:customernotification@icici.bank.in subject:"Bank Statement from" has:attachment', ".pdf"),
    "Axis": ("statements@axis.bank.in", 'from:statements@axis.bank.in subject:"Statement for period" has:attachment', ".pdf"),
}

# Credit card statements: card -> (bank, senders, Gmail query). Remove the cards you do not have.
# Each bank's PDF password goes in the Keychain; see README.md, "Credit card statements".
_AXIS_CARD = ("cc.statements@axis.bank.in", "cc.statements@axisbank.com")
_ICICI_CARD = ("credit_cards@icici.bank.in", "credit_cards@icicibank.com")
_FROM_ICICI_CARD = "(from:credit_cards@icici.bank.in OR from:credit_cards@icicibank.com)"
CARD_SOURCES = {
    "HDFC credit card": ("hdfc", ("emailstatements.cards@hdfcbank.bank.in", "emailstatements.cards@hdfcbank.net"),
                         '(from:emailstatements.cards@hdfcbank.bank.in OR from:emailstatements.cards@hdfcbank.net) subject:"Credit Card Statement"'),
    "IndusInd credit card": ("indusind", ("creditcard.estatements@indusind.com",),
                             'from:creditcard.estatements@indusind.com subject:"Credit Card statement"'),
    "Axis credit card": ("axis", _AXIS_CARD, '(from:cc.statements@axis.bank.in OR from:cc.statements@axisbank.com) subject:"Credit Card"'),
    "ICICI credit card": ("icici", _ICICI_CARD, f'{_FROM_ICICI_CARD} subject:"ICICI Bank Credit Card Statement" -subject:"Amazon Pay"'),
    "Amazon Pay ICICI": ("icici", _ICICI_CARD, f'{_FROM_ICICI_CARD} subject:"Amazon Pay ICICI Bank Credit Card Statement"'),
}
CARD_WINDOW = "newer_than:1y"

# Grocery bills you email to yourself (Star Bazaar bill links). Change the subject to match how you send them.
BILL_QUERY = 'from:me subject:"star bazaar"'

DISCOVER_KEYWORDS = ["debited", "credited", "UPI", "spent", "transaction", "paid to"]
