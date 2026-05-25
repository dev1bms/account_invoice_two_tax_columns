# Account Invoice Two Tax Columns

**Version:** 14.0.1.0.0  
**Category:** Accounting

## Overview

This Odoo 14 module adds a second tax column (Tax 2) to customer invoice lines and the invoice PDF report. Tax 1 remains the native `account.move.line.tax_ids` field with standard Odoo behavior. Tax 2 is an additional `tax2_ids` field computed alongside Tax 1.

## Key Features

- **Tax 1** = Native `tax_ids` field (unchanged Odoo behavior, visible as "Taxes")
- **Tax 2** = Additional `tax2_ids` field (new column, separate selection)
- **Tax computation override** - Odoo calculates both Tax 1 and Tax 2 together
- **Posted invoice protection** - Cannot modify taxes on posted invoices
- **Duplicate prevention** - Same tax cannot be in both columns
- **PDF report** - Shows both Tax 1 (from tax_ids) and Tax 2 (from tax2_ids)
- **Safe inheritance** - Preserves Studio customizations on invoice reports

## Architecture

### Robust Two-Column Design with Temporary Merge
```
┌─────────────────────────────────────────────────────────────────────┐
│  UI Layer (User Visible)                                              │
│  ├─ tax_ids (Tax 1 / "Taxes") - Native Odoo field                    │
│  └─ tax2_ids (Tax 2) - Additional Many2many to account.tax           │
├─────────────────────────────────────────────────────────────────────┤
│  Tax Computation (Backend)                                          │
│  ├─ _recompute_tax_lines() temporarily merges tax2_ids into        │
│  │  tax_ids for calculation                                         │
│  ├─ Odoo computes totals with merged taxes (Tax 1 + Tax 2)         │
│  └─ tax_ids restored to Tax 1 only after computation                │
│     (keeps UI clean: Tax 1 column shows only Tax 1 taxes)           │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow
```
During Tax Computation:
tax_ids (Tax 1) ──┐
                  ├──→ Temporarily Merge ──→ Odoo Tax Engine
                  │                        (calculates both)
tax2_ids (Tax 2) ──┘                           │
                                               ↓
                                     Journal Entries Totals
                                               │
After Computation:                              │
tax_ids restored to Tax 1 only ◄───────────────┘
(UI shows Tax 1 and Tax 2 separately)
```

### Why Temporary Merge?
Odoo's tax computation engine only processes the native `tax_ids` field. To include
Tax 2 in calculations while keeping the UI clean (showing Tax 1 and Tax 2 in separate
columns), we:

1. **Before computation**: Merge `tax2_ids` into `tax_ids` temporarily
2. **During computation**: Odoo calculates totals with both taxes
3. **After computation**: Restore `tax_ids` to contain only Tax 1
4. **UI Display**: `tax_ids` shows Tax 1, `tax2_ids` shows Tax 2 separately
5. **PDF**: Both columns display correctly from their respective fields

This ensures:
- ✅ Tax 2 is included in invoice totals and journal entries
- ✅ Tax 1 and Tax 2 appear in separate UI columns
- ✅ PDF shows both columns correctly
- ✅ Posted invoices protected from modification
- ✅ Constraint prevents duplicate tax selection

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
   - **Tax 1 column** (`tax_ids`): Select primary tax (e.g., 15% VAT)
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

**ValidationError** (`@api.constrains('tax_ids', 'tax2_ids')`) when:
- Same tax selected in both Tax 1 and Tax 2 columns
- Checks `tax_ids` vs `tax2_ids`

**UserError** when:
- Attempting to modify `tax_ids` or `tax2_ids` on posted invoice

### Important Design Note

The constraint `_check_no_duplicate_taxes()` validates that no tax exists in both `tax_ids` (Tax 1) and `tax2_ids` (Tax 2).

### Security

Posted invoices (`state = 'posted'`) are protected from tax modifications:
- Cannot add/remove Tax 2
- Cannot change Tax 1
- Consistent with Odoo's native behavior for locked moves

### PDF Report

The report inherits from `account.report_invoice_document`:
- Adds "Tax 2" column beside "Taxes" column:
  - "Taxes" shows `tax_ids` (Tax 1, native)
  - "Tax 2" shows `tax2_ids`
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
