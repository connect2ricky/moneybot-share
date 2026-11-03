import sqlite3
import unittest

from moneybot import db, ledger


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    ledger.migrate(conn)
    db.set_state(conn, "start_date", "2026-10-01")
    ledger.build(conn)
    return conn


def spend(conn, category, payee="SHOP"):
    ledger.add_expense(conn, {"amount": 100, "date": "2026-10-05", "payee": payee, "account": "Axis 1234",
                              "category": category, "subcategory": None})
    ledger.build(conn)


class BudgetCategories(unittest.TestCase):
    def setUp(self):
        self.conn = fresh()

    def test_added_category_is_kept_and_follows_a_rename(self):
        ledger.add_budget_category(self.conn, "Gifts")
        self.assertIn("Gifts", ledger.category_groups(self.conn))
        ledger.rename_category(self.conn, "Gifts", "Presents")
        self.assertEqual(ledger.budget_categories(self.conn), ["Presents"])

    def test_income_category_cannot_be_added(self):
        with self.assertRaises(ValueError):
            ledger.add_budget_category(self.conn, "Salary")

    def test_removing_from_the_list_keeps_the_category(self):
        ledger.add_budget_category(self.conn, "Gifts")
        ledger.remove_budget_category(self.conn, "Gifts")
        self.assertEqual(ledger.budget_categories(self.conn), [])
        self.assertIn("Gifts", ledger.category_groups(self.conn))


class DeleteCategory(unittest.TestCase):
    def setUp(self):
        self.conn = fresh()

    def test_builtin_stays_deleted_after_rebuild_until_added_again(self):
        ledger.add_subcategory(self.conn, "Travel", "Train")
        ledger.delete_category(self.conn, "Travel")
        ledger.migrate(self.conn)
        ledger.build(self.conn)
        self.assertNotIn("Travel", ledger.category_groups(self.conn))
        self.assertNotIn("Travel", ledger.subcategories(self.conn))
        ledger.add_category(self.conn, "Travel")
        ledger.delete_category(self.conn, "Travel")
        ledger.add_budget_category(self.conn, "Travel")
        ledger.migrate(self.conn)
        self.assertIn("Travel", ledger.category_groups(self.conn))

    def test_rule_for_a_deleted_category_waits_uncategorised(self):
        ledger.delete_category(self.conn, "Travel")
        self.conn.execute("DELETE FROM txn_labels")
        ledger.add_expense(self.conn, {"amount": 100, "date": "2026-10-05", "payee": "IRCTC", "account": "Axis 1234",
                                       "category": "Groceries", "subcategory": None})
        self.conn.execute("DELETE FROM txn_labels")
        self.conn.execute("DELETE FROM payee_labels")
        ledger.build(self.conn)
        row = self.conn.execute("SELECT category FROM transactions WHERE payee = 'IRCTC'").fetchone()
        self.assertEqual(row["category"], "Uncategorised")

    def test_refuses_what_is_in_use(self):
        spend(self.conn, "Health")
        ledger.add_budget_category(self.conn, "Gifts")
        ledger.set_budget(self.conn, "Rent", 1000)
        for name in ("Health", "Gifts", "Rent", "Uncategorised", "Salary", "Nope"):
            with self.assertRaises(ValueError, msg=name):
                ledger.delete_category(self.conn, name)
