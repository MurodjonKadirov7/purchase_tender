# -*- coding: utf-8 -*-

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tools import format_amount


@tagged("post_install", "-at_install")
class TestPurchaseTender(TransactionCase):
    """Qabul kriteriyalarini ishga tushirib tekshiradi."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company_currency = cls.company.currency_id

        cls.apple, cls.pear, cls.melon = cls.env["product.product"].create(
            [
                {"name": "Tender Apple", "type": "consu", "purchase_ok": True},
                {"name": "Tender Pear", "type": "consu", "purchase_ok": True},
                {"name": "Tender Melon", "type": "consu", "purchase_ok": True},
            ]
        )
        cls.vendor_1, cls.vendor_2, cls.vendor_3 = cls.env["res.partner"].create(
            [
                {"name": "Tender Vendor 1"},
                {"name": "Tender Vendor 2"},
                {"name": "Tender Vendor 3"},
            ]
        )
        cls.manager = new_test_user(
            cls.env,
            login="tender_manager",
            groups="base.group_user,purchase.group_purchase_manager",
        )
        cls.buyer = new_test_user(
            cls.env,
            login="tender_buyer",
            groups="base.group_user,purchase.group_purchase_user",
        )

    # ------------------------------------------------------------------ yordamchi

    @classmethod
    def _make_po(cls, vendor, lines, currency=None):
        """lines: [(product, qty, price, days_from_today)]"""
        now = fields.Datetime.now()
        return cls.env["purchase.order"].create(
            {
                "partner_id": vendor.id,
                "currency_id": (currency or cls.company_currency).id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": qty,
                            "price_unit": price,
                            "date_planned": fields.Datetime.add(now, days=days),
                        }
                    )
                    for product, qty, price, days in lines
                ],
            }
        )

    def _line(self, order, product):
        return order.order_line.filtered(lambda line: line.product_id == product)

    def _tender_lines(self):
        return self.env["purchase.order.line"].search(
            [("tender_is_candidate", "=", True)]
        )

    # ------------------------------------------------------------------ 3-kriteriya

    def test_candidate_needs_two_orders(self):
        """Mahsulot kamida ikki xil so'rovda bo'lsagina tenderga tushadi."""
        po_1 = self._make_po(self.vendor_1, [(self.apple, 10, 1000, 0)])
        po_2 = self._make_po(
            self.vendor_2, [(self.apple, 150, 800, 0), (self.pear, 5, 50, 0)]
        )
        po_3 = self._make_po(self.vendor_3, [(self.melon, 1, 10, 0)])

        tender = self._tender_lines()
        self.assertIn(self._line(po_1, self.apple), tender)
        self.assertIn(self._line(po_2, self.apple), tender)
        self.assertNotIn(
            self._line(po_2, self.pear),
            tender,
            "Bitta so'rovdagi mahsulot tenderga tushmaydi",
        )
        self.assertNotIn(self._line(po_3, self.melon), tender)

    def test_only_open_states(self):
        """Tasdiqlangan so'rov tenderdan chiqadi (faqat draft va sent qatnashadi)."""
        po_1 = self._make_po(self.vendor_1, [(self.apple, 10, 1000, 0)])
        po_2 = self._make_po(self.vendor_2, [(self.apple, 10, 800, 0)])
        self.assertIn(self._line(po_1, self.apple), self._tender_lines())

        po_2.button_confirm()
        self.assertEqual(po_2.state, "purchase")
        self.assertFalse(
            self._tender_lines(),
            "Bitta ochiq so'rov qolganda mahsulot tenderdan chiqishi kerak",
        )

    def test_sent_state_participates(self):
        po_1 = self._make_po(self.vendor_1, [(self.apple, 10, 1000, 0)])
        po_2 = self._make_po(self.vendor_2, [(self.apple, 10, 800, 0)])
        po_1.write({"state": "sent"})
        tender = self._tender_lines()
        self.assertIn(self._line(po_1, self.apple), tender)
        self.assertIn(self._line(po_2, self.apple), tender)

    def test_zero_quantity_line_is_out(self):
        po_1 = self._make_po(self.vendor_1, [(self.apple, 10, 1000, 0)])
        po_2 = self._make_po(
            self.vendor_2, [(self.apple, 10, 800, 0), (self.pear, 1, 5, 0)]
        )
        self._line(po_2, self.apple).product_qty = 0
        self.assertFalse(self._tender_lines())

    # ------------------------------------------------------------------ 6-kriteriya

    def test_choose_clears_the_other_offers(self):
        """Tanlangach: ko'p qatorli so'rovda qator o'chadi, bir qatorlida qty nolga tushadi."""
        po_1 = self._make_po(
            self.vendor_1, [(self.apple, 10, 1000, 0), (self.pear, 3, 30, 0)]
        )
        po_2 = self._make_po(self.vendor_2, [(self.apple, 150, 800, 0)])
        po_3 = self._make_po(self.vendor_3, [(self.apple, 300, 900, 0)])
        pear_line = self._line(po_1, self.pear)

        winner = self._line(po_3, self.apple)
        winner.with_user(self.manager).action_tender_choose()

        self.assertFalse(
            self._line(po_1, self.apple),
            "Boshqa mahsuloti bor so'rovda tender qatori o'chirilishi kerak",
        )
        self.assertTrue(pear_line.exists(), "Boshqa mahsulot qatoriga tegilmaydi")
        self.assertEqual(pear_line.product_qty, 3)

        po_2_line = self._line(po_2, self.apple)
        self.assertTrue(po_2_line.exists(), "Yagona qator o'chirilmaydi")
        self.assertEqual(
            po_2.state, "cancel", "Yagona qatorli so'rovning o'zi bekor qilinadi"
        )
        self.assertEqual(
            po_2_line.product_qty, 150, "Taklif miqdori tarix uchun joyida qoladi"
        )

        self.assertEqual(winner.product_qty, 300, "Tanlangan qator o'zgarmaydi")
        self.assertEqual(po_3.state, "draft", "Tanlangan so'rov holati o'zgarmaydi")
        self.assertFalse(self._tender_lines(), "Mahsulot tenderdan chiqadi")

    def test_choose_writes_to_the_chatter(self):
        po_1 = self._make_po(self.vendor_1, [(self.apple, 10, 1000, 0)])
        po_2 = self._make_po(self.vendor_2, [(self.apple, 10, 800, 0)])
        before = len(po_2.message_ids)
        self._line(po_2, self.apple).with_user(self.manager).action_tender_choose()
        self.assertGreater(
            len(po_2.message_ids), before, "Tanlov chatterga yozilishi kerak"
        )

    # ------------------------------------------------------------------ 7-kriteriya

    def test_cancel_drops_only_that_offer(self):
        po_1 = self._make_po(
            self.vendor_1, [(self.apple, 10, 1000, 0), (self.pear, 3, 30, 0)]
        )
        po_2 = self._make_po(self.vendor_2, [(self.apple, 150, 800, 0)])
        po_3 = self._make_po(self.vendor_3, [(self.apple, 300, 900, 0)])

        self._line(po_1, self.apple).with_user(self.manager).action_tender_cancel()
        self.assertFalse(self._line(po_1, self.apple))
        self.assertTrue(self._line(po_1, self.pear).exists())

        tender = self._tender_lines()
        self.assertEqual(
            tender,
            self._line(po_2, self.apple) + self._line(po_3, self.apple),
            "Qolgan ikki taklif tenderda qoladi",
        )

        self._line(po_2, self.apple).with_user(self.manager).action_tender_cancel()
        self.assertEqual(
            po_2.state, "cancel", "Yagona qatorli so'rovning o'zi bekor qilinadi"
        )
        self.assertEqual(
            self._line(po_2, self.apple).product_qty,
            150,
            "Taklif miqdori tarix uchun joyida qoladi",
        )
        self.assertEqual(po_3.state, "draft", "Qolgan so'rovga tegilmaydi")
        self.assertFalse(
            self._tender_lines(), "Bitta taklif qolganda mahsulot tenderdan chiqadi"
        )

    # ------------------------------------------------------------------ 4-kriteriya

    def test_best_lines(self):
        """Eng arzon, eng erta va eng ko'p qatorlar belgilanadi."""
        # (mahsulot, miqdor, narx, bugundan necha kun keyin keladi)
        po_1 = self._make_po(self.vendor_1, [(self.apple, 10, 1000, 0)])
        po_2 = self._make_po(self.vendor_2, [(self.apple, 150, 800, 30)])
        po_3 = self._make_po(self.vendor_3, [(self.apple, 300, 900, 15)])
        line_1 = self._line(po_1, self.apple)
        line_2 = self._line(po_2, self.apple)
        line_3 = self._line(po_3, self.apple)

        best_price, best_date, best_qty = self.env[
            "purchase.order.line"
        ].get_tender_best_lines()

        self.assertEqual(best_price, line_2.ids, "Eng past birlik narxi")
        self.assertEqual(best_date, line_1.ids, "Eng erta yetkazish")
        self.assertEqual(best_qty, line_3.ids, "Eng katta miqdor")

    def test_best_lines_ties_are_all_marked(self):
        po_1 = self._make_po(self.vendor_1, [(self.apple, 10, 800, 0)])
        po_2 = self._make_po(self.vendor_2, [(self.apple, 10, 800, 0)])
        best_price, _best_date, best_qty = self.env[
            "purchase.order.line"
        ].get_tender_best_lines()
        expected = (self._line(po_1, self.apple) + self._line(po_2, self.apple)).ids
        self.assertCountEqual(best_price, expected)
        self.assertCountEqual(best_qty, expected)

    # ------------------------------------------------------------------ 5-kriteriya

    def test_price_converted_to_company_currency(self):
        """Boshqa valyutadagi taklif kompaniya valyutasida solishtiriladi."""
        # Faol bo'lmagan valyutalar odatda ko'rinmaydi — active_test o'chiriladi.
        foreign = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([("id", "!=", self.company_currency.id)], limit=1)
        )
        self.assertTrue(foreign, "Sinov uchun ikkinchi valyuta topilmadi")
        foreign.active = True
        self.env["res.currency.rate"].search(
            [("currency_id", "=", foreign.id), ("company_id", "=", self.company.id)]
        ).unlink()
        self.env["res.currency.rate"].create(
            {
                "currency_id": foreign.id,
                "company_id": self.company.id,
                "rate": 2.0,
                "name": fields.Date.context_today(self.env["res.currency.rate"]),
            }
        )
        po_local = self._make_po(self.vendor_1, [(self.apple, 10, 60, 0)])
        po_foreign = self._make_po(
            self.vendor_2, [(self.apple, 10, 100, 0)], currency=foreign
        )
        line_foreign = self._line(po_foreign, self.apple)

        self.assertEqual(po_foreign.currency_rate, 2.0)
        self.assertAlmostEqual(
            line_foreign.tender_price_unit_cc,
            50.0,
            msg="100 chet valyuta / 2.0 kurs = 50 kompaniya valyutasi",
        )
        # Yorliq: "<taklif valyutasida> (<kompaniya valyutasida>)".
        self.assertEqual(
            line_foreign.tender_price_label,
            "%s (%s)"
            % (
                format_amount(self.env, 100.0, foreign),
                format_amount(self.env, 50.0, self.company_currency),
            ),
            "Valyuta farq qilsa qavs ichida kompaniya valyutasi ko'rinadi",
        )

        best_price, _best_date, _best_qty = self.env[
            "purchase.order.line"
        ].get_tender_best_lines()
        self.assertEqual(
            best_price,
            line_foreign.ids,
            "50 < 60, ya'ni chet valyutadagi taklif arzonroq",
        )

    def test_price_label_without_conversion(self):
        po_1 = self._make_po(self.vendor_1, [(self.apple, 10, 1000, 0)])
        po_2 = self._make_po(self.vendor_2, [(self.apple, 10, 800, 0)])
        label = self._line(po_1, self.apple).tender_price_label
        self.assertNotIn("(", label, "Bir xil valyutada qavs bo'lmaydi")
        self.assertTrue(self._line(po_2, self.apple).tender_price_label)

    # ------------------------------------------------------------------ 9-kriteriya

    def test_only_manager_can_act(self):
        po_1 = self._make_po(self.vendor_1, [(self.apple, 10, 1000, 0)])
        po_2 = self._make_po(self.vendor_2, [(self.apple, 10, 800, 0)])
        line = self._line(po_2, self.apple)

        with self.assertRaises(UserError, msg="Oddiy xarid xodimi tanlay olmaydi"):
            line.with_user(self.buyer).action_tender_choose()
        with self.assertRaises(UserError, msg="Oddiy xarid xodimi bekor qila olmaydi"):
            line.with_user(self.buyer).action_tender_cancel()

        # Ko'rish esa taqiqlanmagan.
        self.assertTrue(
            self.env["purchase.order.line"]
            .with_user(self.buyer)
            .search([("tender_is_candidate", "=", True)])
        )
        self.assertTrue(self._line(po_1, self.apple).exists())
