import json
import sqlite3
import unittest

from moneybot import db, groceries, ledger


def base36(n):
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if not n:
            return out


def bill_page(items, paid, bill_type="Billing", number="100"):
    objs = []

    def add(value):
        objs.append(value)
        return base36(len(objs) - 1)

    def obj(values):
        return add({k: add(v) for k, v in values.items()})

    refs = [obj({"code": i["code"], "description": i["name"], "productName": f"001 APP {i.get('unit', 'KG')}",
                 "quantity": str(i["qty"]), "sellingPrice": str(i["price"]), "mrp": str(i["price"]),
                 "amount": str(i["amount"]), "voidItem": i.get("void", False)}) for i in items]
    bill = {
        "billInfo": obj({"billType": bill_type, "billNumber": number, "purchaseDate": "20261008", "purchaseTime": "115127"}),
        "paymentInfo": obj({"paidAmount": str(paid)}),
        "items": add(refs),
    }
    add(bill)
    return f'<html><script type="qwik/json">{json.dumps({"objs": objs})}</script></html>'


GUAVA = {"code": "1", "name": "GUAVA JMB PNK KG", "qty": 2, "price": 100, "amount": 200.0}
BAG = {"code": "2", "name": "CARRY BAG18*24", "qty": 1, "price": 19, "amount": 19.0, "unit": "PC"}
URL = "https://starbazaar.karnival.com/q/zd/sbAbC123/?ch=3"


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    ledger.migrate(conn)
    db.set_state(conn, "start_date", "2026-10-01")
    ledger.build(conn)
    return conn


def pay(conn, payee, amount, day, subcategory=None):
    if subcategory and subcategory not in ledger.subcategories(conn).get("Groceries", []):
        ledger.add_subcategory(conn, "Groceries", subcategory)
    ledger.add_expense(conn, {"amount": amount, "date": day, "payee": payee, "account": "Axis 1234",
                              "category": "Groceries", "subcategory": subcategory})
    ledger.build(conn)


class Parse(unittest.TestCase):
    def test_reads_items_and_cleans_names(self):
        bill = groceries.parse_star(bill_page([GUAVA, BAG], 219.0))
        self.assertEqual(bill["id"], "star:100")
        self.assertEqual(bill["total"], 219.0)
        self.assertEqual(bill["items"][0]["name"], "Guava Jmb Pnk")
        self.assertEqual((bill["items"][0]["unit"], bill["items"][1]["unit"]), ("KG", "PC"))

    def test_items_that_do_not_add_up_are_refused(self):
        with self.assertRaisesRegex(ValueError, "add up"):
            groceries.parse_star(bill_page([GUAVA], 500.0))

    def test_a_voided_item_does_not_count(self):
        bill = groceries.parse_star(bill_page([GUAVA, {**BAG, "void": True}], 200.0))
        self.assertEqual(len(bill["items"]), 1)

    def test_a_return_is_not_a_purchase(self):
        with self.assertRaisesRegex(ValueError, "not a purchase"):
            groceries.parse_star(bill_page([GUAVA], 200.0, bill_type="Return"))

    def test_a_changed_page_is_reported(self):
        with self.assertRaisesRegex(ValueError, "changed"):
            groceries.parse_star("<html>nothing here</html>")


class Links(unittest.TestCase):
    def test_only_the_shops_own_links_are_opened(self):
        conn = fresh()
        opened = []

        def fake(url):
            opened.append(url)
            return bill_page([GUAVA], 200.0)

        text = f"{URL} https://evil.example/q/zd/x https://starbazaar.karnival.com.evil.example/q/zd/x"
        self.assertEqual(groceries.fetch_links(conn, text, "e1", 1, fake), 1)
        self.assertEqual(opened, [URL])

    def test_a_link_is_read_once_and_a_failure_is_tried_again(self):
        conn = fresh()

        def broken(url):
            raise ValueError("the link could not be opened")

        groceries.fetch_links(conn, URL, "e1", 1, broken)
        self.assertEqual(len(groceries.summary(conn)["problems"]), 1)
        self.assertEqual(groceries.fetch_links(conn, URL, "e1", 1, lambda u: bill_page([GUAVA], 200.0)), 1)
        self.assertEqual(groceries.fetch_links(conn, URL, "e1", 1, broken), 0)


class Summary(unittest.TestCase):
    def setUp(self):
        self.conn = fresh()
        pay(self.conn, "STAR BAZAAR", 219, "2026-10-08", "Stores")
        pay(self.conn, "SURESH DAIRY", 500, "2026-10-09", "Milk")
        pay(self.conn, "EGG STALL R", 100, "2026-10-10")
        groceries.fetch_links(self.conn, URL, "e1", 1, lambda u: bill_page([GUAVA, BAG], 219.0))

    def month(self):
        return groceries.summary(self.conn)["months"]["2026-10"]

    def test_totals_come_from_payments_and_bills_add_nothing(self):
        m = self.month()
        self.assertEqual(m["total"], 819)
        self.assertEqual(m["billed"], 219)
        self.assertEqual({s["name"]: s["amount"] for s in m["subcategories"]},
                         {"Stores": 219, "Milk": 500, "No subcategory": 100})

    def test_a_new_subcategory_in_spending_shows_here(self):
        key = self.conn.execute("SELECT key FROM transactions WHERE payee = 'EGG STALL R'").fetchone()["key"]
        ledger.add_subcategory(self.conn, "Groceries", "Eggs")
        ledger.decide(self.conn, [{"key": key, "category": "Groceries", "subcategory": "Eggs"}])
        ledger.build(self.conn)
        eggs = next(s for s in self.month()["subcategories"] if s["name"] == "Eggs")
        self.assertEqual((eggs["amount"], eggs["payees"]), (100, ["EGG STALL R"]))

    def test_a_bill_finds_its_payment(self):
        self.assertTrue(self.month()["bills"][0]["matched"])
        self.assertEqual(groceries.summary(self.conn)["problems"], [])

    def test_a_bill_with_no_payment_is_flagged(self):
        groceries.fetch_links(self.conn, URL + "x", "e2", 1, lambda u: u)
        groceries.store(self.conn, {"id": "star:9", "ts": 1791000000, "total": 77.0, "items": []})
        self.assertTrue(any("No matching payment" in p["message"] for p in groceries.summary(self.conn)["problems"]))

    def test_item_groups_are_suggested_and_can_be_changed(self):
        self.assertEqual({g["name"] for g in self.month()["groups"]}, {"Fruit", "Carry bags"})
        groceries.set_group(self.conn, "1", "Other")
        self.assertIn("Other", {g["name"] for g in self.month()["groups"]})

    def test_an_item_keeps_its_price_history(self):
        groceries.store(self.conn, {"id": "star:2", "ts": 1791900000, "total": 180.0, "items": [
            {"line": 0, "code": "1", "name": "Guava", "unit": "KG", "quantity": 2, "price": 90, "mrp": 90, "amount": 180.0}]})
        guava = next(i for i in self.month()["items"] if i["code"] == "1")
        self.assertEqual([h["price"] for h in guava["history"]], [100, 90])


if __name__ == "__main__":
    unittest.main()
