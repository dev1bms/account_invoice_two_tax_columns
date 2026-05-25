# Account Invoice Two Tax Columns

**Version:** 14.0.1.0.0
**Category:** Accounting
**Odoo Version:** 14

## Overview

Adds a second tax column (**Tax 2**) on customer invoice lines alongside the
standard Odoo *Taxes* column. Tax 2 is a real `account.tax` record and is
included in all accounting computations: line totals, invoice totals, dynamic
tax lines, posted journal entries, and the PDF report.

## Architecture

```
account.move.line
├── tax_ids   (native field) ──► visible as "Taxes" column (Tax 1)
└── tax2_ids  (new Many2many) ──► visible as "Tax 2" column

Computation hooks (read-only union, no permanent merge):
  • account.move.line._get_price_total_and_subtotal
      → passes (tax_ids | tax2_ids) to account.tax.compute_all
      → makes line.price_total/price_subtotal include Tax 2
  • account.move._recompute_tax_lines
      → temporarily merges tax2_ids into tax_ids
      → super() builds the real tax journal lines
      → tax_ids is restored in a try/finally so the UI stays clean
```

### Why this design?

Odoo 14's tax engine only reads `tax_ids`. We must therefore include Tax 2
in `tax_ids` during the actual calculation — but only during the calculation.
After every computation, `tax_ids` is restored to contain only Tax 1, so:

- The "Taxes" column on the invoice form never shows Tax 2.
- The "Tax 2" column never shows Tax 1.
- Existing invoices keep their original `tax_ids` and get an empty `tax2_ids`.
- No data migration is required.

## Features

- Two visible tax columns on invoice lines: **Taxes** (native) and **Tax 2**.
- Tax 2 selectable from the standard `account.tax` records (no auto-creation).
- Domain filters Tax 2 by `type_tax_use` (sale/purchase) to match the move type.
- Tax 2 included in invoice line `price_total`, invoice `amount_tax`, and
  `amount_total`.
- Posted invoices have separate journal lines for Tax 1 and Tax 2.
- PDF report shows Tax 1 (from `tax_ids`) and Tax 2 (from `tax2_ids`) in
  distinct columns.
- Validation: a tax cannot appear in both columns of the same line.
- Posted invoice protection: `tax2_ids` cannot be modified after posting.

## Installation

```bash
cp -r account_invoice_two_tax_columns /path/to/odoo/addons/
```

Then in Odoo: *Apps → Update Apps List → install* **Account Invoice Two Tax
Columns**.

## Usage

1. Create the Tax 2 account.tax record manually (e.g. 2.1% sale tax) in
   *Accounting → Configuration → Taxes*.
2. Open a customer invoice and add a product line.
3. Select the normal tax in **Taxes** (e.g. 5%).
4. Select the additional tax in **Tax 2** (e.g. 2.1%).
5. Save. The invoice total reflects both taxes.
6. Post. The journal entry contains two separate tax lines.

## Validation Steps (post-install)

1. Install or update the module.
2. Create an invoice with one line: subtotal `100`, Tax 1 `5%`, Tax 2 `2.1%`.
3. Confirm:
   - `Untaxed Amount = 100.00`
   - `Tax 5% = 5.00`
   - `Tax 2.1% = 2.10`
   - `Total = 107.10`
4. Post the invoice. Open *Journal Items* → both tax lines exist.
5. Reopen the invoice form → the "Taxes" column still shows only `5%` and
   the "Tax 2" column still shows only `2.1%`. No cross-pollution.
6. Print the PDF → Tax 1 and Tax 2 appear in separate columns.

## File Layout

```
account_invoice_two_tax_columns/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── account_move_line.py          # tax2_ids field + computation hooks
├── views/
│   └── account_move_views.xml        # adds Tax 2 column to invoice/JE trees
├── reports/
│   └── report_invoice_document.xml   # adds Tax 2 column to invoice PDF
├── tests/
│   ├── __init__.py
│   └── test_invoice_two_tax_columns.py
├── README.md
└── MANUAL_TESTS.md
```

## Constraints

- **ValidationError** `@api.constrains('tax_ids', 'tax2_ids')`:
  the same tax may not be present in both columns of a line.
- **UserError** on `write({'tax2_ids': ...})` if the move is posted.

## Uninstall

1. Make sure no draft invoices rely on Tax 2.
2. Uninstall the module. The `tax2_ids` column is dropped; `tax_ids` is
   untouched on every existing invoice.
