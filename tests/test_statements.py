import sqlite3
import unittest
from datetime import datetime

from moneybot import db, ledger, statements

HEAD = "Transaction Statement for +910000000000\nDuration,01 Oct 2026 - 31 Oct 2026\n\n" \
       "Date,Time,Transaction Details,Transaction ID,UTR,Transaction Type,Credit/debit instrument,Amount\n"
FOOT = '\nThis is an automatically generated statement.\n"Do not fall prey to fictitious offers, etc."\n'


def csv_of(*rows):
    return (HEAD + "\n".join(rows) + FOOT).encode()


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    ledger.migrate(conn)
    db.set_state(conn, "start_date", "2026-10-01")
    return conn


def alert(conn, ref, amount, day="2026-10-05"):
    ts = int(datetime.strptime(day, "%Y-%m-%d").timestamp()) + 3600
    body = f"Amount Debited: INR {amount:.2f} Account Number: XX1234 Date & Time: 05-10-26 Transaction Info: UPI/P2M/{ref}/SHOP"
    conn.execute("INSERT INTO emails(id, thread_id, sender, subject, internal_ts, snippet, body) VALUES(?,?,?,?,?,?,?)",
                 (ref, ref, "fake", "x", ts, "", body))


def manual(conn, amount, day, account="Cash", payee="Netflix"):
    ledger.add_expense(conn, {"amount": amount, "date": day, "payee": payee, "account": account, "category": "Groceries"})


def txn(conn, where):
    return conn.execute(f"SELECT * FROM transactions WHERE {where}").fetchall()


class Parse(unittest.TestCase):
    def test_reads_rows_and_skips_footer(self):
        period, rows = statements.parse_phonepe(
            csv_of("2026-10-01,\t12:34,Paid to STAR BAZAAR,T1,818819772774,Debit,XXXX001234,1651.06").decode())
        self.assertEqual(period, "01 Oct 2026 - 31 Oct 2026")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["amount"], rows[0]["direction"]), (1651.06, "debit"))
        self.assertEqual(statements.payee_of(rows[0]["details"]), "STAR BAZAAR")

    def test_a_changed_format_is_an_error_not_a_partial_import(self):
        conn = fresh()
        statements.store(conn, "e1", "PhonePe", "a.csv", 1, b"something else entirely")
        statements.store(conn, "e2", "PhonePe", "a.csv", 1, csv_of("2026-10-01,12:34,Paid to X,T1,1,Refund,XX39,10"))
        errors = [r["error"] for r in conn.execute("SELECT error FROM statement_files")]
        self.assertTrue(all(errors))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM statement_rows").fetchone()[0], 0)


    def test_a_statement_without_a_csv_says_so(self):
        conn = fresh()
        statements.store(conn, "e1", "PhonePe", "", 1, None)
        self.assertIn("CSV", conn.execute("SELECT error FROM statement_files").fetchone()[0])


AXIS = """Statement of Account No :916010000001234 for the period (From : 01-10-2026  To : 31-10-2026)
OPENING BALANCE              1000.00
01-10-2026 ACME TECHNOLOG/BY SAL
5000.00            6000.00 289
02-10-2026
UPI/P2M/664026564274/CRED Club
/paymen/AXIS BANK
1500.00            4500.00 289
Legends : ICONN - Transaction through Internet Banking
03-10-2026
UPI/P2A/777632319055/SURESH DAIRY
/Paymen/BANK OF INDIA
500.00            4000.00 289 TRANSACTION TOTAL 2000.00 5000.00
CLOSING BALANCE            4000.00
"""


class Axis(unittest.TestCase):
    def test_direction_comes_from_the_balance(self):
        period, rows = statements.parse_axis(AXIS)
        self.assertEqual(period, "01-10-2026 to 31-10-2026")
        self.assertEqual([r["direction"] for r in rows], ["credit", "debit", "debit"])
        self.assertEqual(rows[1]["utr"], "664026564274")
        self.assertEqual(rows[1]["instrument"], "XXXX001234")
        self.assertEqual(statements.payee_of(rows[2]["details"]), "SURESH DAIRY")

    def test_a_row_that_does_not_add_up_rejects_the_file(self):
        with self.assertRaisesRegex(ValueError, "does not add up"):
            statements.parse_axis(AXIS.replace("1500.00 ", "1400.00 "))

    def test_totals_that_do_not_match_reject_the_file(self):
        with self.assertRaisesRegex(ValueError, "totals"):
            statements.parse_axis(AXIS.replace("CLOSING BALANCE            4000.00", "CLOSING BALANCE            4100.00"))


ICICI = """Statement of Transactions in Savings Account Number: 277700001111 in INR for the period October 01, 2026 - October 31, 2026
DATE MODE** PARTICULARS DEPOSITS WITHDRAWALS BALANCE
01-10-2026 B/F 1,000.00
01-10-2026
UPI/ARUN KUMA/XX3881@axl/Payment fr/AXIS
BANK/199103222221/AXL10f70db4e18446b7b314c
23560ce226cARUN KUMAR REDDY SHARMA
500.00 1,500.00
01-10-2026 DEBIT CARD VPS/5024 DMART/202610011200/627406177433/HYDERABAD 200.00 1,300.00
05-10-2026
UPI/RAJU REDDY/XX5961@ybl/Payment fr/YES
BANK
L/088966359178/IBL5bb246baad204d4796e7d7cfb8
6eabe0RAJU REDDY CHICKEN SHOP
300.00 1,000.00
Page 1 of
2
Your Base Branch: ADDAGUTTA
TOTAL 500.00 500.00 1,000.00
"""


class Icici(unittest.TestCase):
    def test_reads_rows_with_direction_reference_and_payee(self):
        period, rows = statements.parse_icici(ICICI)
        self.assertEqual(period, "October 01, 2026 - October 31, 2026")
        self.assertEqual([r["direction"] for r in rows], ["credit", "debit", "debit"])
        self.assertEqual(rows[2]["utr"], "088966359178")
        self.assertEqual(rows[1]["utr"], "")
        self.assertEqual(statements.payee_of(rows[2]["details"]), "RAJU REDDY")
        self.assertEqual(rows[0]["instrument"], "XXXX001111")

    def test_totals_that_do_not_match_reject_the_file(self):
        with self.assertRaisesRegex(ValueError, "totals"):
            statements.parse_icici(ICICI.replace("TOTAL 500.00 500.00", "TOTAL 500.00 600.00"))

    def test_a_row_that_does_not_add_up_rejects_the_file(self):
        with self.assertRaisesRegex(ValueError, "does not add up"):
            statements.parse_icici(ICICI.replace("300.00 1,000.00", "350.00 1,000.00"))

    def test_a_statement_puts_an_app_payment_on_its_real_account(self):
        conn = fresh()
        ts = int(datetime(2026, 10, 27, 12).timestamp())
        body = "You paid\n\u20b9500\nPaid to\nSmoke savings\nBank reference Number\n910676043006"
        conn.execute("INSERT INTO emails(id, thread_id, sender, subject, internal_ts, snippet, body) VALUES('j', 'j', 'noreply@jupiter.money', 'x', ?, '', ?)", (ts, body))
        conn.execute("INSERT INTO statement_rows VALUES('i1', 'e1', 'ICICI', ?, 'debit', 500.0, 'UPI/APSPL/x/910676043006/y', '910676043006', 'XXXX001111')", (ts,))
        conn.execute("INSERT INTO balance_anchors(account, ts, amount) VALUES('ICICI 111', 1, 1000)")
        ledger.build(conn)
        row = txn(conn, "ref = '910676043006'")
        self.assertEqual([r["account"] for r in row], ["ICICI 111"])


class Check(unittest.TestCase):
    def load(self, conn, *rows, email="e1"):
        statements.store(conn, email, "PhonePe", "a.csv", 1, csv_of(*rows))
        ledger.build(conn)

    def outcome(self, conn, txn_id):
        return conn.execute("SELECT outcome FROM statement_results WHERE txn_id = ?", (txn_id,)).fetchone()[0]

    def test_missing_payment_waits_for_review(self):
        conn = fresh()
        self.load(conn, "2026-10-05,12:00,Paid to STAR BAZAAR,T1,111,Debit,XXXX001234,500.00")
        row = txn(conn, "payee = 'STAR BAZAAR'")[0]
        self.assertEqual((row["status"], row["channel"], row["app"]), ("pending", "Statement", "PhonePe"))

    def test_missing_credit_also_waits_for_review(self):
        conn = fresh()
        self.load(conn, "2026-10-05,12:00,Received from Asha,T1,111,Credit,XXXX001234,500.00")
        self.assertEqual(txn(conn, "payee = 'Asha'")[0]["status"], "pending")

    def test_hand_typed_entry_is_not_duplicated_and_answers_only_once(self):
        conn = fresh()
        manual(conn, 649, "2026-10-13")
        self.load(conn, "2026-10-13,21:36,Paid to NETFLIX,T1,111,Debit,XXXX001234,649.00",
                  "2026-10-14,10:00,Paid to NETFLIX,T2,222,Debit,XXXX001234,649.00")
        self.assertEqual(self.outcome(conn, "T1"), "manual")
        self.assertEqual(self.outcome(conn, "T2"), "added")

    def test_one_payment_on_two_statements_matches_one_entry_once(self):
        conn = fresh()
        manual(conn, 649, "2026-10-13")
        statements.store(conn, "e1", "PhonePe", "a.csv", 2,
                         csv_of("2026-10-13,21:36,Paid to NETFLIX,T1,111,Debit,XXXX001234,649.00"))
        conn.execute("INSERT INTO statement_rows VALUES('axis1', 'e2', 'Axis', ?, 'debit', 649.0, 'UPI/P2M/111/NETFLIX', '111', 'XXXX001234')",
                     (conn.execute("SELECT ts FROM statement_rows").fetchone()[0],))
        ledger.build(conn)
        self.assertEqual(len(txn(conn, "amount = 649")), 1)

    def test_same_amount_far_apart_is_a_different_payment(self):
        conn = fresh()
        manual(conn, 649, "2026-10-01")
        self.load(conn, "2026-10-13,21:36,Paid to NETFLIX,T1,111,Debit,XXXX001234,649.00")
        self.assertEqual(self.outcome(conn, "T1"), "added")

    def test_overlapping_statements_add_a_payment_once(self):
        conn = fresh()
        row = "2026-10-05,12:00,Paid to STAR BAZAAR,T1,111,Debit,XXXX001234,500.00"
        self.load(conn, row, email="e1")
        self.load(conn, row, email="e2")
        self.assertEqual(len(txn(conn, "payee = 'STAR BAZAAR'")), 1)

    def test_transfer_to_own_account_is_a_self_transfer(self):
        conn = fresh()
        self.load(conn, "2026-10-05,12:00,Paid to XXXXXXXXXX53,T1,111,Debit,XXXX001234,900.00",
                  "2026-10-06,12:00,Paid to Shop,T2,222,Debit,XXXXXXXXXX53,10.00")
        self.assertEqual(txn(conn, "ref = '111'")[0]["category"], "Self transfer")

    def test_rows_before_tracking_started_are_ignored(self):
        conn = fresh()
        self.load(conn, "2026-09-05,12:00,Paid to Old,T1,111,Debit,XXXX001234,500.00")
        self.assertEqual(self.outcome(conn, "T1"), "early")
        self.assertEqual(txn(conn, "payee = 'Old'"), [])

    def test_payment_the_user_deleted_is_reported_and_stays_deleted(self):
        conn = fresh()
        self.load(conn, "2026-10-05,12:00,Paid to STAR BAZAAR,T1,111,Debit,XXXX001234,500.00", email="e1")
        ledger.delete(conn, txn(conn, "payee = 'STAR BAZAAR'")[0]["key"])
        ledger.build(conn)
        self.assertEqual(self.outcome(conn, "T1"), "deleted")
        self.assertEqual(statements.summaries(conn)[0]["deleted"], 1)

    def test_a_fully_overlapped_older_statement_is_not_announced(self):
        conn = fresh()
        row = "2026-10-05,12:00,Paid to STAR BAZAAR,T1,111,Debit,XXXX001234,500.00"
        statements.store(conn, "new", "PhonePe", "a.csv", 2, csv_of(row))
        statements.store(conn, "old", "PhonePe", "a.csv", 1, csv_of(row))
        ledger.build(conn)
        self.assertEqual([s["id"] for s in statements.summaries(conn)], ["new"])

    def test_a_deleted_row_stays_deleted(self):
        conn = fresh()
        self.load(conn, "2026-10-05,12:00,Paid to STAR BAZAAR,T1,111,Debit,XXXX001234,500.00")
        ledger.delete(conn, txn(conn, "payee = 'STAR BAZAAR'")[0]["key"])
        ledger.build(conn)
        self.assertEqual(txn(conn, "payee = 'STAR BAZAAR'"), [])


class Budgets(unittest.TestCase):
    def test_a_month_replaces_the_default_and_zero_means_none(self):
        conn = fresh()
        ledger.build(conn)
        ledger.set_budget(conn, "Groceries", 1000)
        ledger.set_budget(conn, "Groceries", 1500, "2099-01")
        ledger.set_budget(conn, "Groceries", 0, "2099-02")
        self.assertEqual(ledger.budgets(conn), {"Groceries": 1000})
        self.assertEqual(ledger.budget_months(conn), {"2099-01": {"Groceries": 1500}, "2099-02": {"Groceries": 0}})
        ledger.set_budget(conn, "Groceries", None, "2099-01")
        self.assertNotIn("2099-01", ledger.budget_months(conn))

    def test_changing_a_default_keeps_past_months_as_they_were(self):
        conn = fresh()
        manual(conn, 100, "2026-01-05")
        db.set_state(conn, "start_date", "2026-01-01")
        ledger.build(conn)
        conn.execute("INSERT INTO budgets(category, amount) VALUES('Groceries', 1000)")
        ledger.set_budget(conn, "Groceries", 2000)
        self.assertEqual(ledger.budget_months(conn)["2026-01"]["Groceries"], 1000)
        self.assertEqual(ledger.budgets(conn)["Groceries"], 2000)

    def test_a_month_budget_follows_a_renamed_category(self):
        conn = fresh()
        ledger.set_budget(conn, "Groceries", 500, "2099-01")
        ledger.rename_category(conn, "Groceries", "Provisions")
        self.assertEqual(ledger.budget_months(conn), {"2099-01": {"Provisions": 500}})

    def test_a_bad_month_or_amount_is_refused(self):
        conn = fresh()
        with self.assertRaises(ValueError):
            ledger.set_budget(conn, "Groceries", 500, "soon")
        with self.assertRaises(ValueError):
            ledger.set_budget(conn, "Groceries", -5)


class Accounts(unittest.TestCase):
    def pot_payment(self, conn, ref, amount, day):
        ts = int(datetime.strptime(day, "%Y-%m-%d").timestamp()) + 3600
        bank = f"Amount Debited: INR {amount:.2f}\nAccount Number: XX1234\nTransaction Info: UPI/P2M/{ref}/APSPL/x/y"
        jupiter = f"You paid\n\u20b9{amount:.0f}\nPaid to\nSmoke savings\nBank reference Number\n{ref}"
        for mail, sender, body in ((f"b{ref}", "alerts@axis.bank.in", bank), (f"j{ref}", "noreply@jupiter.money", jupiter)):
            conn.execute("INSERT INTO emails(id, thread_id, sender, subject, internal_ts, snippet, body) VALUES(?,?,?,?,?,?,?)",
                         (mail, mail, sender, "x", ts, "", body))

    def balance(self, conn, account):
        return next(b for b in ledger.balances(conn) if b["account"] == account)

    def test_pot_deposits_add_to_jupiter_without_touching_spending(self):
        conn = fresh()
        self.pot_payment(conn, "111", 125, "2026-10-05")
        self.pot_payment(conn, "222", 250, "2026-10-06")
        ledger.build(conn)
        self.assertIsNone(self.balance(conn, ledger.POT_ACCOUNT)["balance"])
        start = int(datetime(2026, 10, 5, 12).timestamp())
        conn.execute("INSERT INTO balance_anchors(account, ts, amount) VALUES(?, ?, 1000)", (ledger.POT_ACCOUNT, start))
        self.assertEqual(self.balance(conn, ledger.POT_ACCOUNT)["balance"], 1250)
        self.assertEqual(len(txn(conn, f"account = '{ledger.POT_ACCOUNT}'")), 0)
        self.assertEqual(len(txn(conn, "payee LIKE 'Jupiter pot:%'")), 2)

    def test_cash_has_a_balance_that_payments_lower(self):
        conn = fresh()
        manual(conn, 200, "2026-10-13")
        ledger.build(conn)
        ledger.set_balance(conn, "Cash", 5000)
        self.assertEqual(self.balance(conn, "Cash")["balance"], 5000)
        conn.execute("UPDATE balance_anchors SET ts = ?", (int(datetime(2026, 10, 1).timestamp()),))
        self.assertEqual(self.balance(conn, "Cash")["balance"], 4800)


if __name__ == "__main__":
    unittest.main()
