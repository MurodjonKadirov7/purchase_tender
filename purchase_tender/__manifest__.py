# -*- coding: utf-8 -*-
{
    "name": "Purchase Tender",
    "version": "19.0.2.4.0",
    "category": "Purchase",
    "summary": "Compare every open RFQ offer product by product and award "
    "one vendor in a click",
    "description": """
Purchase Tender
===============
A **Tender** menu in the Purchase app that gathers, product by product, every
offer sitting in an open request for quotation.

A product enters the tender as soon as two or more different RFQs of the same
company ask for it. For each product the list shows one row per RFQ with the
vendor, the expected arrival, the unit price and the quantity. The earliest
arrival, the lowest unit price and the largest quantity are highlighted in
green, so the best offer is visible without reading a single number.

Offers in different currencies
------------------------------
A price is compared in the company currency, converted with the order's own
rate, and the column shows both: ``800.00 USD (10 120 000.00 UZS)``. Vendors
quoting in different currencies can be put side by side.

Two actions for a purchase manager
----------------------------------
* **Choose** awards the product to that RFQ. On every other RFQ the line for
  the same product is removed; an RFQ left without any other line is
  cancelled. The chosen RFQ keeps its own status and is untouched.
* **Cancel** drops that single offer with the same rule, leaving the other
  offers in the tender.

Both actions ask for confirmation first and write what happened into the
chatter of every request they touched, so the decision is on record.

Independent of Purchase Agreements
----------------------------------
Built on the standard Purchase application only. It does not depend on
``purchase_requisition``, and shares no field, method or view with it, so both
can be used side by side or on their own.
    """,
    "author": "todoo.uz",
    "website": "https://todoo.uz",
    "license": "OPL-1",
    "price": 5,
    "currency": "USD",
    "support": "info@todoo.uz",
    "depends": ["purchase"],
    "data": [
        "views/purchase_tender_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "purchase_tender/static/src/tender_list_renderer.js",
            "purchase_tender/static/src/tender_list_view.js",
        ],
    },
    "images": [
        "static/description/banner.png",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
