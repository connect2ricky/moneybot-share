import base64
import re
from collections import Counter
from email.utils import parseaddr
from html.parser import HTMLParser

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from . import cards, db, groceries, statements
from .config import (
    CREDENTIALS_FILE,
    DISCOVER_KEYWORDS,
    SCOPES,
    BILL_QUERY,
    CARD_SOURCES,
    CARD_WINDOW,
    SENDER_DOMAINS,
    STATEMENT_SOURCES,
    TOKEN_FILE,
)

# Re-read a day of already-synced mail so late-delivered messages are not missed.
OVERLAP_SECONDS = 24 * 3600


class SignInExpired(Exception):
    """The saved Gmail sign-in can no longer be renewed without the user approving it again."""


def _save(creds):
    TOKEN_FILE.write_text(creds.to_json())
    TOKEN_FILE.chmod(0o600)


def _browser_sign_in():
    if not CREDENTIALS_FILE.exists():
        raise SystemExit(f"Missing {CREDENTIALS_FILE.name}. See README.md for the one-time Google setup.")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0)
    _save(creds)
    return creds


def _credentials(interactive: bool):
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES) if TOKEN_FILE.exists() else None
    if creds and creds.valid:
        return creds
    if creds and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save(creds)
            return creds
        except RefreshError as exc:
            if not interactive:
                raise SignInExpired("Gmail sign-in has expired. Sign in again to fetch new emails.") from exc
            return _browser_sign_in()
    if not interactive:
        raise SignInExpired("No Gmail sign-in saved yet. Sign in to Gmail to fetch new emails.")
    return _browser_sign_in()


def service(interactive: bool = True):
    return build("gmail", "v1", credentials=_credentials(interactive), cache_discovery=False)


def sign_in():
    """Run the Google sign-in in a browser window and save the result. Blocks until the user finishes."""
    _browser_sign_in()


class _TextExtractor(HTMLParser):
    SKIP = {"style", "script", "head", "title"}
    BLOCK = {"p", "div", "br", "tr", "li", "table", "h1", "h2", "h3", "td"}

    def __init__(self):
        super().__init__()
        self.chunks = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BLOCK:
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1

    def handle_data(self, data):
        if not self.skipping:
            self.chunks.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return "".join(parser.chunks)


def _clean(text: str) -> str:
    text = text.replace("\xa0", " ").replace("‌", "")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _decode(part) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


def _collect(part, found):
    mime = part.get("mimeType", "")
    if mime in ("text/plain", "text/html"):
        found[mime] += _decode(part)
    for child in part.get("parts", []):
        _collect(child, found)


def extract_body(payload) -> str:
    found = {"text/plain": "", "text/html": ""}
    _collect(payload, found)
    plain = _clean(found["text/plain"])
    from_html = _clean(html_to_text(found["text/html"])) if found["text/html"] else ""
    # Bank mails often ship a stub plain-text part next to the real HTML body.
    return from_html if len(from_html) > len(plain) else plain


def _header(msg, name):
    for h in msg["payload"].get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _list_ids(svc, query):
    token = None
    while True:
        resp = (
            svc.users()
            .messages()
            .list(userId="me", q=query, pageToken=token, maxResults=500)
            .execute(num_retries=8)
        )
        for m in resp.get("messages", []):
            yield m["id"]
        token = resp.get("nextPageToken")
        if not token:
            return


def sync(since_ts: int | None = None, interactive: bool = True) -> tuple[int, int]:
    """Fetch new alert emails. Returns (new, already_stored)."""
    conn = db.connect()
    last = db.get_state(conn, "last_internal_ts")
    if since_ts is None:
        if last is None:
            raise SystemExit("First run: pass --since YYYY-MM-DD.")
        since_ts = int(last) - OVERLAP_SECONDS

    senders = " OR ".join(SENDER_DOMAINS)
    query = f"from:({senders}) after:{since_ts}"
    svc = service(interactive)

    known = {r["id"] for r in conn.execute("SELECT id FROM emails")}
    new = skipped = 0
    for mid in _list_ids(svc, query):
        if mid in known:
            skipped += 1
            continue
        msg = svc.users().messages().get(userId="me", id=mid, format="full").execute(num_retries=8)
        ts = int(msg["internalDate"]) // 1000
        conn.execute(
            "INSERT INTO emails(id, thread_id, sender, subject, internal_ts, snippet, body) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (
                mid,
                msg.get("threadId"),
                parseaddr(_header(msg, "From"))[1].lower(),
                _header(msg, "Subject"),
                ts,
                msg.get("snippet", ""),
                extract_body(msg["payload"]),
            ),
        )
        new += 1
        if new % 25 == 0:
            conn.commit()
            print(f"  fetched {new}...")
    # Taken from the table, not this run, so an interrupted earlier run cannot leave it stale.
    newest = conn.execute("SELECT MAX(internal_ts) FROM emails").fetchone()[0]
    if newest:
        db.set_state(conn, "last_internal_ts", newest)
    conn.commit()
    fetch_statements(conn, svc)
    fetch_cards(conn, svc)
    fetch_bills(conn, svc)
    return new, skipped


def fetch_bills(conn, svc) -> int:
    """Read bill links the user emailed to themselves. Returns how many bills were read."""
    own = svc.users().getProfile(userId="me").execute(num_retries=8)["emailAddress"].lower()
    done = {r["email_id"] for r in conn.execute(
        "SELECT email_id FROM bill_links GROUP BY email_id HAVING COUNT(error) = 0"
    )}
    start = db.get_state(conn, "start_date", "1970-01-02").replace("-", "/")
    found = 0
    for mid in [m for m in _list_ids(svc, f"{BILL_QUERY} after:{start}") if m not in done]:
        msg = svc.users().messages().get(userId="me", id=mid, format="full").execute(num_retries=8)
        if parseaddr(_header(msg, "From"))[1].lower() == own:
            found += groceries.fetch_links(conn, extract_body(msg["payload"]), mid, int(msg["internalDate"]) // 1000)
    return found


def _attachments(part):
    if part.get("filename") and part.get("body", {}).get("attachmentId"):
        yield part
    for child in part.get("parts", []):
        yield from _attachments(child)


def fetch_statements(conn, svc) -> int:
    """Download statement files not stored yet. Returns how many arrived."""
    done = {r["email_id"] for r in conn.execute("SELECT email_id FROM statement_files WHERE error IS NULL")}
    found = 0
    start = db.get_state(conn, "start_date", "1970-01-02").replace("-", "/")
    for source, (sender, query, extension) in STATEMENT_SOURCES.items():
        # Gmail lists newest first, so where statements overlap a row belongs to the newest one.
        for mid in [m for m in _list_ids(svc, f"{query} after:{start}") if m not in done]:
            msg = svc.users().messages().get(userId="me", id=mid, format="full").execute(num_retries=8)
            if parseaddr(_header(msg, "From"))[1].lower() != sender:
                continue
            ts = int(msg["internalDate"]) // 1000
            files = [p for p in _attachments(msg["payload"]) if p["filename"].lower().endswith(extension)]
            content, name = None, ""
            if files:
                name = files[0]["filename"]
                att = svc.users().messages().attachments().get(
                    userId="me", messageId=mid, id=files[0]["body"]["attachmentId"]
                ).execute(num_retries=8)
                content = base64.urlsafe_b64decode(att["data"])
            statements.store(conn, mid, source, name, ts, content)
            found += 1
    return found


def fetch_cards(conn, svc) -> int:
    """Download credit card statements not stored yet. Returns how many were read."""
    done = {r["email_id"] for r in conn.execute("SELECT email_id FROM card_statements WHERE error IS NULL")}
    found = 0
    for card, (bank, senders, query) in CARD_SOURCES.items():
        secret = cards.password(bank)
        for mid in [m for m in _list_ids(svc, f"{query} has:attachment {CARD_WINDOW}") if m not in done]:
            msg = svc.users().messages().get(userId="me", id=mid, format="full").execute(num_retries=8)
            if parseaddr(_header(msg, "From"))[1].lower() not in senders:
                continue
            ts = int(msg["internalDate"]) // 1000
            if secret is None:
                cards.store(conn, mid, card, ts, error="password not saved in the Keychain")
                continue
            files = [p for p in _attachments(msg["payload"]) if p["filename"].lower().endswith(".pdf")]
            if not files:
                continue
            att = svc.users().messages().attachments().get(
                userId="me", messageId=mid, id=files[0]["body"]["attachmentId"]
            ).execute(num_retries=8)
            cards.add(conn, mid, card, bank, ts, base64.urlsafe_b64decode(att["data"]), secret)
            found += 1
    return found


def discover(since_ts: int) -> Counter:
    """Count senders of transaction-looking mail, regardless of SENDER_DOMAINS."""
    keywords = " ".join(f'"{k}"' for k in DISCOVER_KEYWORDS)
    query = f"{{{keywords}}} after:{since_ts} -category:promotions -category:social"
    svc = service()
    counts = Counter()
    for mid in _list_ids(svc, query):
        msg = (
            svc.users()
            .messages()
            .get(userId="me", id=mid, format="metadata", metadataHeaders=["From"])
            .execute(num_retries=8)
        )
        counts[parseaddr(_header(msg, "From"))[1].lower()] += 1
    return counts
