import sqlite3
import unittest

from moneybot import cards, db, ledger

AXIS = """PAYMENT SUMMARY
Total Payment Due Minimum Payment Due Statement Period Payment Due Date Statement Generation Date
23/09/2026 - 21/10/2026 10/11/2026 21/10/2026600.00   Dr 500.00   Dr
Auto-Debit facility on 18605005555400000******1111 1,000.00 400.00 68.99
Previous Balance - Payments - Credits + Purchase + Cash Advance + Other Debit&Charges =Total Payment Due
100.00  Dr 100.00 0.00 0.00 0.00 600.00 600.00   Dr
27/09/2026 EMI PRINCIPAL - 15/48, REF# 1           CASH WITHDRAWAL 600.00 Dr
01/10/2026 BBPS PAYMENT RECEIVED - DP2    100.00 Cr
"""

HDFC = """TOTAL AMOUNT DUE
C2,441.00
MINIMUM DUE
C200.00
DUE DATE
02 Nov, 2026
PREVIOUS STATEMENT DUES PAYMENTS/CREDITSRECEIVED PURCHASES/DEBIT(Current Billing Cycle) FINANCE CHARGES
C100.00 C100.00 C2,441.00 C0.00
TOTAL CREDIT LIMIT
(Including Cash) AVAILABLE CREDIT LIMIT AVAILABLE CASH LIMIT
C6,49,000 C5,42,178 C2,59,600
400000XXXXXX2222
13 Oct, 2026
14 Sep, 2026 - 13 Oct, 2026
01/10/2026| 09:36 BPPY CC PAYMENT DP2 (Ref#ST1) +  C 100.00 l
06/10/2026| 14:04 ANTHROPIC* CLAUDE SUBSAN FRANCISC + 30  C 2,399.00 l
07/10/2026| 00:00 1.75% on all DCC Transaction (Ref# ST2)  C 41.98 l
"""

INDUSIND = """ 100.00 DR
 0.00
 700.00
 100.00
 04/11/2026
 16/09/2026 To 15/10/2026
 15/10/2026
 5,00,000.00 4,97,843.74 1,00,000.00 1,00,000.00
 700.00 DR
 70.00
 2,156.26 DR
MR A
4000XXXXXXXX3333 (Mention your full Credit Card No.)
01/10/2026 BBPS PAYMENT 0 100.00 CR
31/03/2026 MYNTRA BANGALORE IND DEPARTMENTAL
STORES
 56 700.00 DR
"""

CORAL = """`100.00
`1,464.99
SPENDS OVERVIEW
January 20, 2026
February 7, 2026
4000XXXXXXXX4444
21/12/2025 12556722318 IRCTC E-TICKET NEW DELHI IN 29 1,464.99
Available Cash
`6,70,000.00 `5,72,307.99 `67,000.00 `0.00
Statement period : November 21, 2025 to January 20, 2026
Previous Balance Purchases / Charges Cash Advances Payments / Credits
`0.00 `1,464.99 `0.00 `0.00
"""


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    return conn


class Parse(unittest.TestCase):
    def test_axis(self):
        s = cards.parse_axis(AXIS)
        self.assertEqual((s["last4"], s["due_date"], s["total_due"], s["min_due"]), ("1111", "2026-11-10", 600.0, 500.0))
        self.assertEqual(s["rows"][0]["details"], "EMI PRINCIPAL - 15/48, REF# 1")
        self.assertTrue(s["rows"][1]["credit"])
        self.assertTrue(cards.balanced(s))

    def test_hdfc_reward_points_are_not_a_credit(self):
        s = cards.parse_hdfc(HDFC)
        self.assertEqual([r["credit"] for r in s["rows"]], [True, False, False])
        self.assertEqual(s["credit_limit"], 649000.0)
        self.assertEqual(s["statement_date"], "2026-10-13")

    def test_indusind_row_can_wrap(self):
        s = cards.parse_indusind(INDUSIND)
        self.assertEqual(s["rows"][1]["details"], "MYNTRA BANGALORE IND DEPARTMENTAL STORES")
        self.assertEqual((s["total_due"], s["min_due"]), (700.0, 70.0))
        self.assertTrue(cards.balanced(s))

    def test_icici_total_is_the_larger_figure(self):
        s = cards.parse_icici(CORAL)
        self.assertEqual((s["total_due"], s["min_due"]), (1464.99, 100.0))
        self.assertEqual((s["statement_date"], s["due_date"]), ("2026-01-20", "2026-02-07"))
        self.assertTrue(cards.balanced(s))

    def test_unknown_layout_is_refused(self):
        with self.assertRaises(cards.CardStatementError):
            cards.parse_axis("something else")


def row(details, amount=100.0, credit=False):
    return {"details": details, "amount": amount, "credit": credit}


class Emis(unittest.TestCase):
    def test_principal_and_interest_make_one_emi(self):
        rows = [row("EMI INTEREST - 15/48, REF# 595", 20.0), row("EMI PRINCIPAL - 15/48, REF# 595", 80.0), row("LATE FEE", 3.6)]
        out = cards.emis(rows, {})
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["amount"], out[0]["interest"], out[0]["number"], out[0]["left"]), (100.0, 20.0, 15, 33))
        self.assertEqual([r["emi"] for r in rows], [True, True, False])
        self.assertEqual(rows[0]["emi_number"], "15/48")

    def test_hdfc_purchase_with_emi_in_its_name_is_not_an_instalment(self):
        rows = [row("EMI IBIBO GROUP PRIVATE LGURGAON", 12069.79), row("EMI AMAZON PAY INDIA PRIVAwww.amazon.i")]
        self.assertEqual(cards.emis(rows, {}), [])
        self.assertEqual([r["emi"] for r in rows], [False, False])

    def test_hdfc_tenure_comes_from_the_loan_summary(self):
        rows = [row("OFFUS EMI,PRIN NB:17,00000700000001 (Ref# 1)", 5477.0), row("OFFUS EMI,INT NBR:17,00000700000001 (Ref# 2)", 147.0),
                row("SMARTEMI ,PRIN NB:04,00000700000002 (Ref# 3)", 3849.0), row("SMARTEMI ,INT NBR:04,00000700000002 (Ref# 4)", 1137.0)]
        out = cards.emis(rows, {"700000001": 18, "700000002": 24})
        self.assertEqual([(e["name"], e["amount"], e["left"]) for e in out], [("Purchase EMI", 5624.0, 1), ("SmartEMI", 4986.0, 20)])

    def test_hdfc_merchant_emi_joins_its_cut_short_loan_number(self):
        rows = [row("EMI M-18M RELIANCE DIGITAL,P:10,0001777", 2674.0), row("MER EMI ,INT NBR:10,00000177770036 (Ref# 1)", 383.0)]
        out = cards.emis(rows, {})
        self.assertEqual([(e["name"], e["amount"], e["tenure"], e["left"]) for e in out], [("Reliance Digital", 3057.0, 18, 8)])

    def test_icici_plans_stay_apart(self):
        rows = [row("Principal Amount Amortization - <15/24>", 400.0), row("Interest Amount Amortization - <15/24>", 50.0),
                row("Principal Amount Amortization - <17/24>", 410.0), row("Interest Amount Amortization - <17/24>", 40.0)]
        self.assertEqual(len(cards.emis(rows, {})), 2)

    def test_indusind_two_rows_with_different_names_are_one_emi(self):
        rows = [row("EMI PRIN FOR AMAZON PAY INDIA (005/006)", 1054.85), row("EMI INT-AMAZON PAY INDIA PRIV (005/006)", 28.31)]
        out = cards.emis(rows, {})
        self.assertEqual([(e["amount"], e["left"]) for e in out], [(1083.16, 1)])

    def test_a_reversal_is_not_an_instalment(self):
        self.assertEqual(cards.emis([row("EMI PRINCIPAL - 1/3, REF# 6", 10.0, credit=True)], {}), [])


class EmiGst(unittest.TestCase):
    def test_gst_billed_with_the_interest_joins_the_emi(self):
        rows = [row("EMI PRINCIPAL - 15/48, REF# 5", 3831.01), row("EMI INTEREST - 15/48, REF# 5", 2013.45), row("GST", 362.42)]
        out = cards.emis(rows, {})
        self.assertEqual((out[0]["gst"], out[0]["amount"]), (362.42, 6206.88))
        self.assertTrue(rows[2]["emi"])

    def test_gst_on_something_else_is_counted_as_gst_on_fees(self):
        rows = [row("EMI PRINCIPAL - 15/48, REF# 5", 3831.01), row("EMI INTEREST - 15/48, REF# 5", 2013.45),
                row("IGST-VPS1-RATE 18.0 -36 (Ref#1)", 7.56), row("GST", 17.82)]
        out = cards.emis(rows, {})
        self.assertEqual(out[0]["gst"], 0.0)
        self.assertEqual([(e["name"], e["amount"]) for e in out if e["number"] is None], [("GST on fees", 25.38)])
        self.assertEqual([r["emi_number"] for r in rows[2:]], ["GST", "GST"])

    def test_hdfc_gst_comes_from_the_statement_before(self):
        earlier = cards.emis([row("SMARTEMI ,PRIN NB:03,00000700000002 (Ref# 1)", 3802.0),
                              row("SMARTEMI ,INT NBR:03,00000700000002 (Ref# 2)", 1184.0)], {"700000002": 24})
        rows = [row("SMARTEMI ,PRIN NB:04,00000700000002 (Ref# 3)", 3849.0), row("SMARTEMI ,INT NBR:04,00000700000002 (Ref# 4)", 1137.0),
                row("IGST-VPS2725744296459-RATE 18.0 -36 (Ref#1)", 213.12)]
        out = cards.emis(rows, {"700000002": 24}, earlier)
        self.assertEqual((out[0]["gst"], out[0]["amount"]), (213.12, 5199.12))

    def test_gst_after_the_last_instalment_is_still_an_emi_cost(self):
        earlier = cards.emis([row("OFFUS EMI,PRIN NB:18,00000700000003 (Ref# 1)", 1874.0),
                              row("OFFUS EMI,INT NBR:18,00000700000003 (Ref# 2)", 23.0)], {"700000003": 18})
        out = cards.emis([row("IGST-VPS1-RATE 18.0 -36 (Ref#1)", 4.14)], {}, earlier)
        self.assertEqual([(e["number"], e["left"], e["principal"], e["amount"]) for e in out], [(18, 0, 0.0, 4.14)])


class Store(unittest.TestCase):
    def setUp(self):
        self.conn = fresh()

    def test_summary_lists_statements_and_problems(self):
        cards.store(self.conn, "1", "Axis Rewards", 1, cards.parse_axis(AXIS))
        cards.store(self.conn, "2", "IndusInd Legend", 1, skipped=True)
        cards.store(self.conn, "3", "Axis Neo", 1, error="password not saved in the Keychain")
        out = cards.summary(self.conn)
        self.assertEqual([s["card"] for s in out["statements"]], ["Axis Rewards"])
        self.assertEqual(len(out["statements"][0]["rows"]), 2)
        self.assertEqual(out["problems"], [{"card": "Axis Neo", "message": "password not saved in the Keychain", "count": 1}])

    def test_a_bill_payment_is_told_apart_from_a_refund(self):
        statement = cards.parse_axis(AXIS)
        statement["rows"].append({"date": "2026-10-02", "details": "PNB*IRCTC Ticketing", "amount": 5.0, "credit": True})
        cards.store(self.conn, "1", "Axis Rewards", 1, statement)
        rows = cards.summary(self.conn)["statements"][0]["rows"]
        self.assertEqual([r["payment"] for r in rows if r["credit"]], [True, False])

    def test_igst_rows_read_as_gst(self):
        statement = cards.parse_axis(AXIS)
        statement["rows"].append({"date": "2026-10-02", "details": "IGST-VPS1-RATE 18.0 -36 (Ref#1)", "amount": 5.0, "credit": False})
        cards.store(self.conn, "1", "Axis Rewards", 1, statement)
        self.assertEqual(cards.summary(self.conn)["statements"][0]["rows"][-1]["label"], "GST")

    def test_a_later_read_replaces_the_error(self):
        cards.store(self.conn, "1", "Axis Rewards", 1, error="password not saved in the Keychain")
        cards.store(self.conn, "1", "Axis Rewards", 1, cards.parse_axis(AXIS))
        self.assertEqual(cards.summary(self.conn)["problems"], [])

    def test_a_figure_that_does_not_add_up_is_flagged(self):
        s = cards.parse_axis(AXIS)
        s["total_due"] = 900.0
        cards.store(self.conn, "1", "Axis Rewards", 1, s)
        self.assertFalse(cards.summary(self.conn)["statements"][0]["balanced"])

    def test_statements_do_not_reach_the_ledger(self):
        ledger.migrate(self.conn)
        db.set_state(self.conn, "start_date", "2026-10-01")
        cards.store(self.conn, "1", "Axis Rewards", 1, cards.parse_axis(AXIS))
        ledger.build(self.conn)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 0)
