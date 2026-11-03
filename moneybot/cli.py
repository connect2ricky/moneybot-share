import argparse
import getpass
import re
from datetime import date, datetime

from pathlib import Path

from . import backup, db, gmail, ledger, loans, phone, web
from .config import SENDER_DOMAINS


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").timestamp())


def _first_of_last_month() -> str:
    today = date.today()
    year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return date(year, month, 1).isoformat()


def cmd_sync(args):
    since = _ts(args.since) if args.since else None
    new, skipped = gmail.sync(since)
    print(f"Done: {new} new emails stored, {skipped} already had.")


def cmd_discover(args):
    counts = gmail.discover(_ts(args.since))
    print(f"{'count':>5}  {'tracked':7}  sender")
    for sender, n in counts.most_common():
        tracked = "yes" if any(d in sender for d in SENDER_DOMAINS) else ""
        print(f"{n:>5}  {tracked:7}  {sender}")


def cmd_summary(args):
    conn = db.connect()
    rows = conn.execute("SELECT sender, subject FROM emails").fetchall()
    groups = {}
    for r in rows:
        shape = re.sub(r"\d[\d,.]*", "#", r["subject"] or "")
        groups[(r["sender"], shape)] = groups.get((r["sender"], shape), 0) + 1
    print(f"{len(rows)} emails stored\n")
    for (sender, shape), n in sorted(groups.items(), key=lambda kv: (kv[0][0], -kv[1])):
        print(f"{n:>4}  {sender}  |  {shape}")


def cmd_show(args):
    conn = db.connect()
    like = f"%{args.match}%"
    rows = conn.execute(
        "SELECT * FROM emails WHERE sender LIKE ? OR subject LIKE ? "
        "ORDER BY internal_ts DESC LIMIT ?",
        (like, like, args.limit),
    ).fetchall()
    for r in rows:
        when = datetime.fromtimestamp(r["internal_ts"]).strftime("%Y-%m-%d %H:%M")
        print("=" * 78)
        print(f"{when}  {r['sender']}\nSubject: {r['subject']}\n")
        print(r["body"])
    print(f"\n{len(rows)} shown")


def _build():
    result = ledger.build(db.connect())
    print(
        f"Ledger: {result['transactions']} transactions, "
        f"{result['merged_duplicates']} duplicate app receipts merged, "
        f"{result['self_transfer_pairs']} self-transfers paired."
    )


def cmd_build(args):
    _build()


def cmd_dashboard(args):
    _build()
    web.serve(args.port)


def cmd_run(args):
    cmd_sync(args)
    cmd_dashboard(args)


def cmd_import_loans(args):
    imported, problems = loans.import_csv(db.connect(), args.path, replace=args.replace)
    print(f"Imported {len(imported)} loans.")
    for problem in problems:
        print("  note:", problem)


def cmd_backup(args):
    try:
        result = backup.make(push=not args.no_push)
    except backup.BackupError as exc:
        raise SystemExit(f"Backup failed: {exc}")
    print(f"Backed up {result['database_bytes'] // 1024} KB as {result['file']} ({result['bytes'] // 1024} KB encrypted).")
    if args.no_push:
        print("Saved locally only.")
    elif result["pushed"]:
        print(f"Pushed to github.com/{backup.BACKUP_REPO}.")
    else:
        print("Saved locally, but the push to GitHub failed. Run the command again when you are online.")


def cmd_restore(args):
    out = Path(args.out) if args.out else db.DB_FILE.with_name(f"restored-{datetime.now():%Y%m%d-%H%M%S}.db")
    try:
        backup.restore(Path(args.file), out)
    except backup.BackupError as exc:
        raise SystemExit(f"Restore failed: {exc}")
    print(f"Decrypted to {out}.")
    print(f"To use it, stop the dashboard and replace {db.DB_FILE} with that file.")


def cmd_phone_key(args):
    print(phone.key())


def cmd_phone_token(args):
    try:
        phone.save_token(getpass.getpass("Paste the read-only GitHub token (hidden): ").strip())
    except backup.BackupError as exc:
        raise SystemExit(str(exc))
    print("Token works and is saved in the macOS Keychain.")


def cmd_phone_publish(args):
    conn = db.connect()
    ledger.build(conn)
    data = web.snapshot(conn)
    data.pop("phone_error")
    try:
        print("Published." if phone.publish(data) else "Nothing to publish.")
    except backup.BackupError as exc:
        raise SystemExit(str(exc))


def main():
    parser = argparse.ArgumentParser(prog="moneybot")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sync", help="fetch new alert emails from Gmail")
    p.add_argument("--since", help="YYYY-MM-DD; required on first run, then optional")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("discover", help="list senders of transaction-looking mail")
    p.add_argument("--since", default=_first_of_last_month())
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("summary", help="stored emails grouped by sender and subject shape")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("show", help="print stored email bodies matching a sender/subject")
    p.add_argument("match")
    p.add_argument("--limit", type=int, default=3)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("build", help="rebuild transactions from stored emails")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("dashboard", help="open the dashboard without fetching mail")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("run", help="fetch new mail, rebuild, and open the dashboard")
    p.add_argument("--since", help="YYYY-MM-DD; only needed on the very first run")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("import-loans", help="load loans from an EMI schedule CSV")
    p.add_argument("path")
    p.add_argument("--replace", action="store_true", help="delete existing loans first")
    p.set_defaults(func=cmd_import_loans)

    p = sub.add_parser("backup", help="encrypt the database and push it to the private backup repository")
    p.add_argument("--no-push", action="store_true", help="save the encrypted file locally without pushing")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("restore", help="decrypt a backup file into a new database file")
    p.add_argument("file", help="a .mbk file from the backup repository")
    p.add_argument("--out", help="where to write the database (default: data/restored-<time>.db)")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("phone-key", help="show the key the phone app needs (creates it the first time)")
    p.set_defaults(func=cmd_phone_key)

    p = sub.add_parser("phone-token", help="check the phone's GitHub token and save it for personal builds")
    p.set_defaults(func=cmd_phone_token)

    p = sub.add_parser("phone-publish", help="send the latest data to the phone app now")
    p.set_defaults(func=cmd_phone_publish)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
