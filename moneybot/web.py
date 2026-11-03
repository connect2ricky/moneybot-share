import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import backup, cards, db, gmail, groceries, ledger, loans, phone, statements

PAGE = Path(__file__).with_name("dashboard.html")
LOANS_PAGE = Path(__file__).with_name("loans.html")
BUDGET_PAGE = Path(__file__).with_name("budget.html")
CARDS_PAGE = Path(__file__).with_name("cards.html")
COLLAPSE_SCRIPT = Path(__file__).with_name("collapse.js")
GROCERY_PAGE = Path(__file__).with_name("grocery.html")
HOST = "127.0.0.1"
PUBLISH_DELAY = 15
_lock = threading.Lock()
_publish_timer = None


def snapshot(conn) -> dict:
    """Everything the dashboard shows, also sent to the phone app."""
    rows = conn.execute(
        "SELECT key, date, account, direction, amount, payee, info, channel, app, "
        "category, subcategory, status, counted, original_amount, note, bank_payee FROM transactions ORDER BY ts DESC"
    ).fetchall()
    return {
        "transactions": [dict(r) for r in rows],
        "categories": ledger.category_groups(conn),
        "subcategories": ledger.subcategories(conn),
        "balances": ledger.balances(conn),
        "last_sync": db.get_state(conn, "last_internal_ts"),
        "loans": loans.all_loans(conn),
        "payments": loans.payments(conn),
        "budgets": ledger.budgets(conn),
        "budget_months": ledger.budget_months(conn),
        "budget_categories": ledger.budget_categories(conn),
        "mandatory": ledger.mandatory_categories(conn),
        "statements": statements.summaries(conn),
        "grocery": groceries.summary(conn),
        "cards": cards.summary(conn),
        "phone_error": db.get_state(conn, "phone_error") or None,
    }


def _publish():
    with _lock:
        conn = db.connect()
        data = snapshot(conn)
    data.pop("phone_error")
    try:
        phone.publish(data)
        error = ""
    except backup.BackupError as exc:
        error = str(exc)
    with _lock:
        conn = db.connect()
        db.set_state(conn, "phone_error", error)
        conn.commit()


def _publish_soon():
    """After a change, once things have settled, so a run of approvals becomes one push."""
    global _publish_timer
    if _publish_timer:
        _publish_timer.cancel()
    _publish_timer = threading.Timer(PUBLISH_DELAY, _publish)
    _publish_timer.daemon = True
    _publish_timer.start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body, content_type="application/json"):
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _local(self) -> bool:
        # Other websites open in the browser must not be able to read or change the ledger.
        port = self.server.server_address[1]
        allowed = {f"{HOST}:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in allowed and (
            origin is None or origin.split("://", 1)[-1] in allowed
        )

    def do_GET(self):
        if not self._local():
            return self._send(403, {"error": "forbidden"})
        if self.path == "/":
            return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/grocery":
            return self._send(200, GROCERY_PAGE.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/collapse.js":
            return self._send(200, COLLAPSE_SCRIPT.read_bytes(), "text/javascript; charset=utf-8")
        if self.path == "/cards":
            return self._send(200, CARDS_PAGE.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/budget":
            return self._send(200, BUDGET_PAGE.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/loans":
            return self._send(200, LOANS_PAGE.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/loans":
            with _lock:
                conn = db.connect()
                return self._send(200, {"loans": loans.all_loans(conn), "payments": loans.payments(conn)})
        if self.path == "/api/data":
            with _lock:
                return self._send(200, snapshot(db.connect()))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._local():
            return self._send(403, {"error": "forbidden"})
        self._post()
        _publish_soon()

    def _post(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/gmail/signin":
                # Not under the lock: it waits for the user in the browser, and the dashboard must keep working meanwhile.
                gmail.sign_in()
                return self._send(200, {"signed_in": True})
            with _lock:
                conn = db.connect()
                result = {}
                if self.path == "/api/backup":
                    # The server cannot ask for a passphrase, so it must already be in the Keychain.
                    return self._send(200, backup.make(interactive=False))
                if self.path.startswith("/api/loans/"):
                    if self.path == "/api/loans/save":
                        loans.save(conn, body)
                    elif self.path == "/api/loans/delete":
                        loans.delete(conn, body["id"])
                    elif self.path == "/api/loans/paid":
                        loans.set_paid(conn, body["ids"], body["month"], body["paid"])
                    else:
                        return self._send(404, {"error": "not found"})
                    return self._send(200, {"loans": loans.all_loans(conn), "payments": loans.payments(conn)})
                if self.path == "/api/decide":
                    ledger.decide(conn, body["items"])
                elif self.path == "/api/edit":
                    ledger.edit(conn, body)
                elif self.path == "/api/balance/include":
                    ledger.set_balance_in_total(conn, body["account"], bool(body["include"]))
                elif self.path == "/api/balance":
                    ledger.set_balance(conn, body["account"], body["amount"])
                elif self.path == "/api/note":
                    ledger.set_note(conn, body["key"], body.get("note"))
                elif self.path == "/api/grocery/group":
                    groceries.set_group(conn, body["code"], body["group"])
                elif self.path == "/api/statements/seen":
                    statements.mark_seen(conn)
                elif self.path == "/api/budget":
                    ledger.set_budget(conn, body["category"], body.get("amount"), body.get("month"))
                elif self.path == "/api/budget/category":
                    ledger.add_budget_category(conn, body["name"])
                elif self.path == "/api/budget/category/remove":
                    ledger.remove_budget_category(conn, body["name"])
                elif self.path == "/api/budget/mandatory":
                    ledger.set_mandatory(conn, body["category"], bool(body["mandatory"]))
                elif self.path == "/api/expense":
                    ledger.add_expense(conn, body)
                elif self.path == "/api/amount":
                    ledger.set_amount(conn, body["key"], body.get("amount"))
                elif self.path == "/api/delete":
                    ledger.delete(conn, body["key"])
                elif self.path == "/api/category/rename":
                    ledger.rename_category(conn, body["old"], body["new"])
                elif self.path == "/api/category/delete":
                    ledger.delete_category(conn, body["name"])
                elif self.path == "/api/category":
                    ledger.add_category(conn, body["name"])
                elif self.path == "/api/subcategory/rename":
                    ledger.rename_subcategory(conn, body["category"], body["old"], body["new"])
                elif self.path == "/api/subcategory":
                    ledger.add_subcategory(conn, body["category"], body["name"])
                elif self.path == "/api/sync":
                    new, _ = gmail.sync(interactive=False)
                    result["new_emails"] = new
                else:
                    return self._send(404, {"error": "not found"})
                ledger.build(conn)
                return self._send(200, {**snapshot(conn), **result})
        except gmail.SignInExpired as exc:
            self._send(401, {"error": str(exc), "reauth": True})
        except backup.BackupError as exc:
            self._send(400, {"error": str(exc)})
        except (KeyError, ValueError, TypeError) as exc:
            self._send(400, {"error": str(exc)})
        except (Exception, SystemExit) as exc:
            self._send(500, {"error": str(exc)})


def serve(port: int = 8765, open_browser: bool = True):
    server = ThreadingHTTPServer((HOST, port), Handler)
    url = f"http://{HOST}:{port}/"
    print(f"Dashboard running at {url}  (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    _publish_soon()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
