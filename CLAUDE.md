# moneybot: notes for Claude

A personal money tracker. It reads bank and UPI alert emails from the user's Gmail
(read-only), stores them in SQLite, and shows a dashboard at http://localhost:8765.
`README.md` is the user's setup guide; keep it accurate when you change behaviour.

## The user's money data is private

- Never commit, print, upload or paste the contents of `credentials.json`, `token.json`,
  anything in `data/` (the database, backups, statements), or any Keychain value.
  All of these are in `.gitignore`; keep it that way.
- Passwords live in the macOS Keychain (`moneybot-statement-*`, `moneybot-backup`,
  `moneybot-phone`, `moneybot-phone-token`). Ask the user to run the
  `security add-generic-password ... -w` commands from the README themselves, so a
  password never appears in the conversation or in a file.
- Gmail access stays read-only (`SCOPES` in `moneybot/config.py`). Never add send,
  modify or delete scopes.
- Tests and examples use made-up names, payees and account numbers, never real ones
  copied from the user's emails.
- Backups and phone data go only to the user's own **private** repository
  (`BACKUP_REPO`). The phone build from `install_personal.sh` contains their token and
  key: never send it to TestFlight, a store, or anyone else.
- Commit or push only when the user asks.

## Commands

```bash
uv sync                                  # install, once
uv run moneybot run --since YYYY-MM-DD   # first run: fetch mail from that date, open dashboard
uv run moneybot run                      # fetch new mail, rebuild, open dashboard
uv run moneybot build                    # rebuild transactions from stored emails
uv run moneybot discover                 # senders of transaction-like mail
uv run moneybot summary                  # stored emails grouped by sender and shape
uv run moneybot show <text>              # print stored emails matching a sender/subject
uv run python -m unittest discover tests # Python tests
cd expense_app && flutter test           # phone app tests
```

The dashboard server re-reads the HTML files on every request, so a page change shows
on reload. Python changes need the server restarted.

## How it fits together

- `gmail.py` fetches alert emails (`SENDER_DOMAINS`) into the `emails` table, plus
  statement attachments, card statements and grocery bills.
- `parsers.py` turns one email into a record: `role` "bank" (the bank's own alert, the
  source of truth) or "enrich" (a UPI app receipt merged into the bank's record).
- `ledger.build()` rebuilds the `transactions` table from scratch every time. A
  transaction's key is `account|direction|ref`, which is how the same payment from
  several emails or a statement is counted once.
- The user's decisions (categories, edits, deletions, budgets) live in their own
  tables and are applied on each rebuild. Never store them only in `transactions`,
  which is dropped and rebuilt.
- Tables: always-needed ones go in `db.SCHEMA`; `ledger.PERSISTENT` holds user decisions;
  `ledger.REBUILT` is dropped on every build.
- `categories.py`: starting categories and keyword `RULES` (first match wins). A payee
  the user has approved before keeps that category.
- `statements.py`: bank statements (PhonePe CSV, Axis and ICICI PDF) are checked against
  the alerts; missing payments are added for review, never silently.
- `cards.py`: credit card statement PDFs for the Cards tab. Each must balance (previous
  balance + rows = total due) or it is flagged. Cards never change spending totals.
- `web.py` serves the pages (`dashboard.html`, `budget.html`, `loans.html`,
  `grocery.html`, `cards.html`) and the JSON API; `snapshot()` is everything they show.
- `phone.py` pushes an encrypted copy of `snapshot()` for the phone app in `expense_app/`
  (Flutter, read-only).

## Common requests

**Setting it up for a new user.** Walk through README sections 1 and 2. The user creates
`credentials.json` in Google Cloud and approves Gmail access in their own browser. Then
run `uv run moneybot discover` to see which of their banks send alerts, and adjust
`SENDER_DOMAINS`, `STATEMENT_SOURCES` and `CARD_SOURCES` in `moneybot/config.py` to match.
Clear out cards they do not have.

**Adding a bank.**
1. Find its alerts: `uv run moneybot summary`, then `uv run moneybot show <sender>`.
   Look at debits and credits, UPI and non-UPI, and any second alert format.
2. Add a function to `parsers.py` returning `role`, `account` (via `_acct("Bank", digits)`),
   `direction` ("debit"/"credit"), `amount`, `payee`, `info`, `channel` and the UPI `ref`
   when there is one; return None for emails that are not transactions.
3. Register the exact sender address in `PARSERS` and the domain in `SENDER_DOMAINS`.
4. Add a test with a made-up email in the bank's format, then `uv run moneybot build` and
   check the dashboard against a few real alerts.

**Changing categories for the user's own people.** Add a line at the top of `RULES` in
`categories.py`, or approve the payee once on the dashboard, which is usually enough.

**Adding a dashboard feature.** Keep the phone app in step: the same figure is usually
worked out in `expense_app/lib/money.dart` and shown in the matching `*_view.dart`.
