# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_amount
from odoo.tools.float_utils import float_compare

MANAGER_GROUP = "purchase.group_purchase_manager"

# Tenderda faqat ochiq so'rovlar qatnashadi: RFQ va RFQ Sent.
# Manba: purchase/models/purchase_order.py:99-106 — state selection ('draft',
# 'sent', 'to approve', 'purchase', 'done', 'cancel').
TENDER_STATES = ("draft", "sent")


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # Diqqat: purchase_requisition o'rnatilsa aynan `company_currency_id` nomli
    # field qo'shadi (purchase_requisition/models/purchase.py:266). Ikki modul
    # bir-biriga tegmasligi uchun bu yerda o'z nom maydonimiz ishlatiladi.
    # Yorliq ham noyob bo'lishi shart: bir modelda bir xil yorliqli ikki field
    # bo'lsa Odoo ogohlantiradi va filtr ro'yxatida ikkisi ajratib bo'lmaydi.
    tender_company_currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        string="Tender Company Currency",
    )
    tender_price_unit_cc = fields.Monetary(
        string="Unit Price in Company Currency",
        currency_field="tender_company_currency_id",
        compute="_compute_tender_price_unit_cc",
        store=True,
        help="Unit price converted with the order's own currency rate, so that "
        "offers made in different currencies can be compared.",
    )
    # Yorliq core `price_unit` ("Unit Price") bilan to'qnashmasligi kerak;
    # ro'yxatdagi ustun sarlavhasi view'da alohida beriladi.
    tender_price_label = fields.Char(
        string="Tender Unit Price",
        compute="_compute_tender_price_label",
        help="Unit price in the order currency, followed by its company "
        "currency value when the two differ.",
    )
    tender_is_candidate = fields.Boolean(
        string="In Tender",
        compute="_compute_tender_is_candidate",
        search="_search_tender_is_candidate",
        help="Technical: the line is an open offer for a product that at least "
        "two different requests for quotation ask for.",
    )

    # ------------------------------------------------------------------ compute

    @api.depends("price_unit", "order_id.currency_rate")
    def _compute_tender_price_unit_cc(self):
        """Birlik narxini kompaniya valyutasiga o'giradi.

        `currency_rate` core `purchase` da store=True
        (purchase/models/purchase_order.py:150-156), shuning uchun qo'shimcha
        bog'liqlik kerak emas. Core ham soliq hisobiga aynan shu kursni beradi
        (purchase/models/purchase_order_line.py:114).
        """
        for line in self:
            rate = line.order_id.currency_rate
            line.tender_price_unit_cc = line.price_unit / rate if rate else 0.0

    # `format_amount` summani foydalanuvchi tiliga qarab yozadi, shuning uchun
    # til kesh kalitiga kirishi shart — aks holda birinchi o'qilgan tildagi
    # ko'rinish qolgan tillarga ham qaytariladi
    # (idioma: account/models/account_move.py:979).
    @api.depends_context("lang")
    @api.depends(
        "price_unit",
        "tender_price_unit_cc",
        "currency_id",
        "tender_company_currency_id",
    )
    def _compute_tender_price_label(self):
        """`800.00 USD` yoki valyuta farq qilsa `800.00 USD (10 120 000.00 UZS)`."""
        for line in self:
            currency = line.currency_id
            if not currency:
                line.tender_price_label = ""
                continue
            label = format_amount(line.env, line.price_unit, currency)
            company_currency = line.tender_company_currency_id
            if company_currency and company_currency != currency:
                label = "%s (%s)" % (
                    label,
                    format_amount(
                        line.env, line.tender_price_unit_cc, company_currency
                    ),
                )
            line.tender_price_label = label

    @api.depends("product_id", "company_id", "state", "product_qty", "display_type")
    def _compute_tender_is_candidate(self):
        pairs = self._tender_candidate_pairs() if self else set()
        for line in self:
            line.tender_is_candidate = bool(
                not line.display_type
                and line.state in TENDER_STATES
                and line.product_qty > 0
                and (line.product_id.id, line.company_id.id) in pairs
            )

    def _search_tender_is_candidate(self, operator, value):
        """Domenda ishlatish uchun.

        Idioma core'dan olingan: faqat `=` / `!=`, natija oddiy domen ro'yxati
        (purchase/models/product.py:106-112 — `_search_is_in_purchase_order`).
        """
        if operator not in ("=", "!="):
            raise ValidationError(self.env._("Unsupported operator"))
        pairs = self._tender_candidate_pairs()
        line_ids = []
        if pairs:
            product_ids = list({product_id for product_id, _company_id in pairs})
            candidates = self.search(
                self._tender_base_domain() + [("product_id", "in", product_ids)]
            )
            line_ids = [
                line.id
                for line in candidates
                if (line.product_id.id, line.company_id.id) in pairs
            ]
        positive = (operator == "=") == bool(value)
        return [("id", "in" if positive else "not in", line_ids)]

    # ------------------------------------------------------------------ tender to'plami

    @api.model
    def _tender_base_domain(self):
        """Tenderga umuman kirishi mumkin bo'lgan qatorlar."""
        return [
            ("display_type", "=", False),
            ("state", "in", list(TENDER_STATES)),
            ("product_qty", ">", 0),
        ]

    @api.model
    def _tender_candidate_pairs(self):
        """{(product_id, company_id)} — kamida ikki xil so'rovda uchragan mahsulotlar.

        `count_distinct` agregati Odoo 18 da mavjud (odoo/models.py:376).
        Kompaniya ham guruhlash kalitida — turli kompaniyalar aralashmaydi.
        """
        groups = self._read_group(
            domain=self._tender_base_domain(),
            groupby=["product_id", "company_id"],
            aggregates=["order_id:count_distinct"],
        )
        return {
            (product.id, company.id)
            for product, company, order_count in groups
            if order_count >= 2
        }

    @api.model
    def get_tender_best_lines(self):
        """[eng arzon, eng erta, eng ko'p] qator id'lari — mahsulot kesimida.

        Front-end shu ro'yxatlar bo'yicha katakchalarni yashil qiladi. Teng
        qiymatlar bo'lsa hammasi belgilanadi.
        """
        lines = self.search([("tender_is_candidate", "=", True)])
        qty_precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        best_price, best_date, best_qty = [], [], []
        groups = defaultdict(lambda: self.browse())
        for line in lines:
            groups[(line.product_id.id, line.company_id.id)] |= line
        for group_lines in groups.values():
            currency = group_lines[0].tender_company_currency_id

            min_price = min(group_lines.mapped("tender_price_unit_cc"))
            best_price += group_lines.filtered(
                lambda l: (
                    currency.compare_amounts(l.tender_price_unit_cc, min_price) == 0
                )
            ).ids

            dated = group_lines.filtered("date_planned")
            if dated:
                min_date = min(dated.mapped("date_planned"))
                best_date += dated.filtered(lambda l: l.date_planned == min_date).ids

            max_qty = max(group_lines.mapped("product_qty"))
            best_qty += group_lines.filtered(
                lambda l: (
                    float_compare(
                        l.product_qty, max_qty, precision_digits=qty_precision
                    )
                    == 0
                )
            ).ids
        return [best_price, best_date, best_qty]

    # ------------------------------------------------------------------ amallar

    def _tender_check_manager(self):
        if not self.env.user.has_group(MANAGER_GROUP):
            raise UserError(
                self.env._("Only a Purchase Manager can award or drop a tender offer.")
            )

    def _tender_drop_line(self):
        """Qatorni tenderdan chiqaradi va nima qilinganini qaytaradi.

        So'rovda boshqa mahsulot qatori ham bo'lsa faqat shu qator o'chiriladi.
        Yagona qator bo'lsa — so'rovning o'zi bekor qilinadi: bo'sh so'rovni
        qoldirishdan ko'ra buni bekor qilgan ma'qul, taklif miqdori esa tarix
        uchun joyida qoladi.

        `button_cancel` core'niki (purchase/models/purchase_order.py:553-557);
        draft/sent so'rovda uning to'sig'i (hisob-faktura) ishlamaydi.
        """
        self.ensure_one()
        product_lines = self.order_id.order_line.filtered(lambda l: not l.display_type)
        if len(product_lines) > 1:
            self.unlink()
            return "removed"
        self.order_id.button_cancel()
        return "cancelled"

    def action_tender_choose(self):
        """Shu taklifni tanlaydi, qolganlarini tozalaydi."""
        self.ensure_one()
        self._tender_check_manager()
        if not self.tender_is_candidate:
            raise UserError(
                self.env._("This offer is no longer part of an open tender.")
            )
        product = self.product_id
        winner = self.order_id
        losers = self.search(
            self._tender_base_domain()
            + [
                ("product_id", "=", product.id),
                ("company_id", "=", self.company_id.id),
                ("id", "!=", self.id),
            ]
        )
        dropped = 0
        for line in losers:
            order = line.order_id
            outcome = line._tender_drop_line()
            dropped += 1
            order.message_post(
                body=self.env._(
                    "Tender: %(product)s was awarded to %(vendor)s on %(order)s. "
                    "%(outcome)s",
                    product=product.display_name,
                    vendor=winner.partner_id.display_name,
                    order=winner.name,
                    outcome=(
                        self.env._("This line has been removed.")
                        if outcome == "removed"
                        else self.env._(
                            "It was the only line, so the request for quotation "
                            "has been cancelled."
                        )
                    ),
                )
            )
        winner.message_post(
            body=self.env._(
                "Tender: %(product)s awarded to %(vendor)s — %(qty)s at %(price)s. "
                "%(count)s competing offer(s) cleared.",
                product=product.display_name,
                vendor=winner.partner_id.display_name,
                qty=self.product_qty,
                price=self.tender_price_label,
                count=dropped,
            )
        )

    def action_tender_cancel(self):
        """Shu taklifni tenderdan olib tashlaydi, qolganlari joyida qoladi."""
        self.ensure_one()
        self._tender_check_manager()
        order = self.order_id
        product = self.product_id
        vendor = order.partner_id
        outcome = self._tender_drop_line()
        order.message_post(
            body=self.env._(
                "Tender: the offer from %(vendor)s for %(product)s was dropped. "
                "%(outcome)s",
                vendor=vendor.display_name,
                product=product.display_name,
                outcome=(
                    self.env._("The line has been removed.")
                    if outcome == "removed"
                    else self.env._(
                        "It was the only line, so the request for quotation "
                        "has been cancelled."
                    )
                ),
            )
        )
