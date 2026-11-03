# moneybot

A personal money tracker for India, built from the bank and UPI alert emails in your
Gmail. It runs on your Mac and opens a dashboard in your browser at
http://localhost:8765. An optional phone app shows the same dashboard.

- **Your data stays on your Mac.** Everything is stored in `data/moneybot.db`. Gmail
  access is read-only, and nothing is sent anywhere unless you set up the optional
  backup and phone sync, which use a private GitHub repository of your own.
- **What it shows:** spending by category and by day, a monthly budget, loans and EMIs,
  credit card statements, and grocery bills.

## What it understands

| Source | What is read |
|---|---|
| Axis, HDFC, ICICI, Jupiter, PhonePe | Transaction alert emails (the main source) |
| PhonePe, Axis and ICICI bank statements | Statements you request, to find missed transactions |
| Axis, HDFC, ICICI, IndusInd credit cards | Monthly card statement PDFs (Cards tab) |
| Star Bazaar | Bill links you email to yourself (Grocery tab) |

Another bank needs a small parser in `moneybot/parsers.py`. See "Adding a bank" below.

## What you need

- A Mac (the Keychain is used for passwords)
- [uv](https://docs.astral.sh/uv/getting-started/installation/), which installs Python for you:
  `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Your Gmail account

## 1. Let it read your Gmail (one time, about 10 minutes)

The app needs its own Google sign-in. You make one for yourself; nobody else can use it.

1. Open https://console.cloud.google.com/ and create a project (any name, for example "moneybot").
2. **APIs & Services → Library**: search for **Gmail API** and click **Enable**.
3. **APIs & Services → OAuth consent screen**: choose **External**, fill in an app name and
   your email, and under **Test users** add your own Gmail address.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**. Choose
   **Desktop app**, then **Download JSON**.
5. Save the downloaded file in this folder as **`credentials.json`**.

Never share `credentials.json`, `token.json` (created at first sign-in) or the `data/` folder.
They are your Gmail access and your money history, and git ignores all three.

Google may ask you to sign in again every week while the app is in "Testing". That is
normal for a personal app.

## 2. First run

```bash
cd moneybot                                  # this folder
uv sync                                      # installs everything, once
uv run moneybot run --since 2026-11-01       # pick the first day you want tracked
```

A browser opens asking you to approve read-only Gmail access, then the dashboard opens.
Every payment out lands in **To review** with a suggested category. Approve them, and the
next payment to the same payee gets the same category automatically.

## 3. Every day

```bash
uv run moneybot run                          # fetch new email and open the dashboard
```

The **Sync** button on the dashboard fetches new email too. Keep the terminal open while
you use the dashboard.

## 4. Make it yours

- **Categories:** add, rename and merge them on the dashboard (Spending page, at the
  bottom). Starting suggestions come from `RULES` in `moneybot/categories.py`. Add your
  own people there, for example `(r"RAVI KUMAR", "Family & Friends")`.
- **Which emails are read:** `SENDER_DOMAINS` in `moneybot/config.py`. Run
  `uv run moneybot discover` to list the senders of transaction-like emails in your inbox.
- **Your own transfers:** a payment to someone with your own name counts as a transfer
  between your accounts, not spending. Your name is read from Axis alert emails, so
  without an Axis account, check transfers on the dashboard.
- **Budget, loans, grocery groups:** all set on the dashboard.

### Bank statements (optional)

When a PhonePe, Axis or ICICI statement arrives by email, the dashboard checks it for
transactions the alerts missed and adds them for review. PDF statements are
password-protected, so save each bank's statement password in the Keychain once:

```bash
security add-generic-password -U -a moneybot -s moneybot-statement-axis -w
security add-generic-password -U -a moneybot -s moneybot-statement-icici -w
```

Each command asks for the password. Ask the bank for a statement by email to use this.

### Credit card statements (optional, Cards tab)

Edit `CARD_SOURCES` in `moneybot/config.py` to list only the cards you have. Then save
each bank's card statement password (the format is printed in the bank's email):

```bash
security add-generic-password -U -a moneybot -s moneybot-statement-axis-card -w
security add-generic-password -U -a moneybot -s moneybot-statement-hdfc-card -w
security add-generic-password -U -a moneybot -s moneybot-statement-icici-card -w
security add-generic-password -U -a moneybot -s moneybot-statement-indusind-card -w
```

The Cards tab is separate from Spending: it never changes your spending totals.

### Grocery bills (optional)

Email Star Bazaar bill links to yourself with "star bazaar" in the subject. Change
`BILL_QUERY` in `moneybot/config.py` if you prefer another subject.

## 5. Backups and the phone app (optional)

Both use a **private** GitHub repository of yours, and everything in it is encrypted on
your Mac first.

1. Install the GitHub CLI and sign in: `brew install gh`, then `gh auth login`.
2. Create a private repository and clone it into the data folder:
   ```bash
   gh repo create moneybot-data --private
   git clone https://github.com/YOUR_GITHUB_USER/moneybot-data.git data/backups
   ```
3. In `moneybot/config.py`, set `BACKUP_REPO = "YOUR_GITHUB_USER/moneybot-data"` and
   `BACKUP_GH_USER = "YOUR_GITHUB_USER"`.
4. Back up any time with `uv run moneybot backup`. The first run asks for a passphrase and
   keeps it in the Keychain. Without that passphrase a backup cannot be opened.

### Phone app

The app in `expense_app/` is a read-only copy of the dashboard. It needs
[Flutter](https://docs.flutter.dev/get-started/install) and, for iPhone, Xcode.

1. Create a key for the phone: `uv run moneybot phone-key`.
2. On GitHub, create a **fine-grained token** with access to only `moneybot-data`,
   permission **Contents: Read-only**. Save it with `uv run moneybot phone-token`.
3. **iPhone:** open `expense_app/ios/Runner.xcworkspace` in Xcode, choose **Runner →
   Signing & Capabilities**, pick your own Team (your Apple ID works) and change the
   Bundle Identifier to something unique, like `com.yourname.moneytracker`.
4. Connect your phone with a cable, unlock it, and run:
   ```bash
   cd expense_app && ./install_personal.sh ios        # or: ./install_personal.sh android
   ```
5. Open the app and tap Sync. The Mac sends new data a few seconds after every change.

With a free Apple ID, an iPhone app stops opening after 7 days. Run the install command
again to renew it. Never share this build: it contains your token and key.

## Adding a bank

Run `uv run moneybot summary` to see your stored alert emails grouped by sender and shape,
and `uv run moneybot show <sender>` to print a few. Add a function to
`moneybot/parsers.py` modelled on the existing ones, register its sender address in
`PARSERS`, add the domain to `SENDER_DOMAINS`, then run `uv run moneybot build`.

## How it counts

- Bank alerts are the source of truth. App receipts (Jupiter, PhonePe) for the same UPI
  reference are merged into the bank's record, not counted twice.
- Payments between your own accounts are transfers, not spending.
- Credit card bill payments count as spending; individual card purchases are listed but
  not counted, so nothing is counted twice.
- Only money paid out counts as spending. Salary is used for "Left from salary".
- Balances are estimates from alerts. Re-enter the real balance from time to time.

## Tests

```bash
uv run python -m unittest discover tests
cd expense_app && flutter test
```
