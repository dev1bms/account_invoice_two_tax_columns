# Account Invoice Two Tax Columns

**Version:** 14.0.1.0.0  
**Category:** Accounting

## Overview

This Odoo 14 module adds a second tax column (Tax 2) to customer invoice lines and the invoice PDF report. Both Tax 1 and Tax 2 are fully functional `account.tax` records that flow through Odoo's native tax engine.

## Key Features

- **Two editable tax columns** on invoice lines: "Tax 1" and "Tax 2"
- **Native Odoo tax computation** - Both taxes merged into hidden `tax_ids` field
- **Clean separation** - `tax1_ids` and `tax2_ids` are UI fields; `tax_ids` is effective/backend
- **Automatic synchronization** - Changes to either column immediately reflected in accounting
- **Posted invoice protection** - Taxes cannot be modified on posted invoices
- **Duplicate prevention** - Same tax cannot be selected in both columns
- **PDF report** - Shows separate Tax 1 and Tax 2 columns
- **Safe inheritance** - Preserves Studio customizations on invoice reports

## Architecture

### Three-Field Design
```
┌─────────────────────────────────────────────────────────┐
│  UI Layer (User Visible)                                │
│  ├─ tax1_ids (Tax 1 column) - Many2many to account.tax │
│  └─ tax2_ids (Tax 2 column) - Many2many to account.tax │
├─────────────────────────────────────────────────────────┤
│  Backend Layer (Odoo Engine)                            │
│  └─ tax_ids (Effective) = tax1_ids + tax2_ids          │
│     Native field used by Odoo for tax computation      │
└─────────────────────────────────────────────────────────┘
```

### Data Flow
```
User changes Tax 1 (tax1_ids) ──┐
                                ├──→ _sync_to_tax_ids() ──→ tax_ids (effective)
User changes Tax 2 (tax2_ids) ──┘
```

The sync ensures:
- `tax_ids` always contains the union of `tax1_ids` + `tax2_ids`
- No duplicate taxes ever exist in `tax_ids`
- Posted invoices are protected from modification
- Constraint prevents same tax in both `tax1_ids` and `tax2_ids`

## Installation

### 1. Copy module to Odoo
```bash
# Copy to Odoo addons directory
cp -r account_invoice_two_tax_columns /opt/odoo/addons/
# Or your specific addons path
```

### 2. Update app list and install
1. Enable Developer Mode
2. Go to Apps → Update Apps List
3. Search "Account Invoice Two Tax Columns"
4. Click Install

### 3. Create Tax 2 record (Accountant task)
1. Go to **Accounting → Configuration → Taxes**
2. Click Create
3. Configure:
   - **Tax Name:** Tax 2 (2.1%) 
   - **Tax Type:** Sales
   - **Tax Computation:** Percentage of Price
   - **Amount:** 2.1
   - **Repartition Lines:** Configure debit/credit accounts (ask your accountant)
4. Save

## Usage

### Creating Invoices with Two Taxes

1. Create new Customer Invoice
2. Add product lines
3. For each line:
   - **Tax 1 column** (`tax1_ids`): Select primary tax (e.g., 15% VAT)
   - **Tax 2 column** (`tax2_ids`): Optionally select secondary tax (e.g., 2.1%)
4. Odoo automatically computes totals using the merged effective taxes (`tax_ids`)
5. Post invoice - journal entries include both tax amounts

**Note**: The native `tax_ids` field is now hidden from UI but remains the effective field used by Odoo's tax engine.

### Supported Line Combinations

| Line | Tax 1 | Tax 2 | Result |
|------|-------|-------|--------|
| A | 15% | - | Taxed 15% only |
| B | - | 2.1% | Taxed 2.1% only |
| C | 15% | 2.1% | Taxed 15% + 2.1% |
| D | - | - | No tax |

## Testing

### Automated Tests
```bash
# Run module tests
./odoo-bin -c odoo.conf -d your_database --test-tags account_invoice_two_tax_columns
```

Tests cover:
- Tax 1 only, Tax 2 only, both, none
- Mixed invoices
- Journal entry verification
- Posted invoice protection
- Duplicate prevention
- Tax preservation when changing Tax 1

### Manual Tests
See `MANUAL_TESTS.md` for complete manual testing procedures.

## Technical Details

### File Structure
```
account_invoice_two_tax_columns/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── account_move_line.py    # Core logic
├── views/
│   └── account_move_views.xml  # Invoice form UI
├── reports/
│   └── report_invoice_document.xml  # PDF report
├── tests/
│   ├── __init__.py
│   └── test_invoice_two_tax_columns.py
├── README.md
└── MANUAL_TESTS.md
```

### Constraints & Validation

**ValidationError** (`@api.constrains('tax1_ids', 'tax2_ids')`) when:
- Same tax selected in both Tax 1 and Tax 2 columns
- Checks `tax1_ids` vs `tax2_ids` (NOT vs `tax_ids`)

**UserError** when:
- Attempting to modify `tax1_ids`, `tax2_ids`, or `tax_ids` on posted invoice

### Important Design Note

The constraint `_check_no_duplicate_taxes()` validates that no tax exists in both `tax1_ids` and `tax2_ids`. This is correct because:
- `tax1_ids` = UI field for Tax 1 column
- `tax2_ids` = UI field for Tax 2 column  
- `tax_ids` = Effective merged field (always contains taxes from both columns)

If we checked `tax_ids` vs `tax2_ids`, every valid invoice with Tax 2 would fail validation since `tax_ids` must contain the Tax 2 taxes!

### Security

Posted invoices (`state = 'posted'`) are protected from tax modifications:
- Cannot add/remove Tax 2
- Cannot change Tax 1
- Consistent with Odoo's native behavior for locked moves

### PDF Report

The report inherits from `account.report_invoice_document`:
- Replaces original single "Taxes" column with two columns:
  - "Tax 1" showing `tax1_ids`
  - "Tax 2" showing `tax2_ids`
- Shows tax name/description per line from respective fields
- Empty cell when line has no tax in that column
- Preserves existing Studio customizations

## Uninstallation

1. Ensure no draft invoices have Tax 2 selected
2. Uninstall module from Apps menu
3. Optional: Archive or delete the Tax 2 tax record

## Troubleshooting

### Tax 2 not appearing in totals
- Verify Tax 2 record has proper repartition line accounts configured
- Check that tax2_ids was saved (visible in form after save)

### Cannot modify taxes on posted invoice
- This is expected behavior (posted invoices are locked)
- Create credit note and new invoice if tax changes needed

### Duplicate tax error
- Remove the tax from one column (either Tax 1 or Tax 2)
- Each tax can only be selected once per line

## Support

For issues or questions:
1. Review `MANUAL_TESTS.md` for expected behavior
2. Check Odoo logs for error details
3. Verify Tax 2 record configuration with accountant

## License

LGPL-3
