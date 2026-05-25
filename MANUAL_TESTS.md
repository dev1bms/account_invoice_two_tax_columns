# Manual Test Steps for Account Invoice Two Tax Columns

## Prerequisites
1. Install the module
2. Create Tax 2 (e.g., 2.1%) manually via Accounting > Configuration > Taxes
   - Name: "Tax 2 (2.1%)"
   - Amount: 2.1
   - Amount Type: Percentage of Price
   - Tax Type: Sales
   - Configure repartition lines with proper accounts (ask accountant)

## Test Scenarios

### Test 1: Line with Tax 1 only (native tax_ids)
1. Create new Customer Invoice
2. Add a product line with price = 100
3. In the standard "Taxes" column (Tax 1), select your standard VAT (e.g., 15%)
4. Leave "Tax 2" column empty
5. **Expected**:
   - Taxes column shows 15% tax
   - Tax 2 column is empty
   - Total = 115 (100 + 15%)
6. Save draft and verify no errors

**Note**: Tax 1 is the native Odoo `tax_ids` field, unchanged behavior.

### Test 2: Line with Tax 2 only
1. Create new Customer Invoice
2. Add a product line with price = 100
3. Leave "Taxes" column (Tax 1) empty
4. In "Tax 2" column, select the 2.1% tax
5. **Expected**:
   - Taxes column is empty
   - Tax 2 column shows the 2.1% tax
   - Total = 102.1 (100 + 2.1%)
6. Save draft

**Design Verification**: Tax 2 (`tax2_ids`) is computed via the overridden `_get_computed_taxes()` method.

### Test 3: Line with Tax 1 + Tax 2
1. Create new Customer Invoice
2. Add a product line with price = 100
3. "Taxes" column (Tax 1) = 15% VAT
4. "Tax 2" column = 2.1% tax
5. **Expected**:
   - Taxes column shows 15%
   - Tax 2 column shows 2.1%
   - Total = 117.1 (100 + 15% + 2.1%)
6. Save draft

**Design Verification**:
- `tax_ids` contains only Tax 1 (15%)
- `tax2_ids` contains only Tax 2 (2.1%)
- `_get_computed_taxes()` returns union of both for Odoo calculation

### Test 4: Invoice without any Tax 2
1. Create new Customer Invoice
2. Add multiple lines with only Tax 1 (no Tax 2)
3. **Expected**: 
   - Tax 2 column can be hidden or left empty
   - Invoice totals are correct
   - PDF prints without Tax 2 column content
4. Save and print PDF to verify

### Test 5: Mixed invoice (all combinations)
1. Create invoice with 3 lines:
   - Line A: Tax 1 = 15%, Tax 2 = empty
   - Line B: Tax 1 = empty, Tax 2 = 2.1%
   - Line C: Tax 1 = 15%, Tax 2 = 2.1%
2. **Expected**: Each line shows correct tax columns
3. Verify totals before posting

### Test 6: Post invoice and verify journal entries
1. Use invoice from Test 3 (Tax 1 + Tax 2)
2. Click "Confirm" to post the invoice
3. Go to Journal Entry (smart button)
4. **Expected**: 
   - Journal entry contains separate lines for both Tax 1 (15%) and Tax 2 (2.1%)
   - Tax amounts are posted to correct tax accounts
   - Total debit = Total credit

### Test 7: Cannot modify taxes on posted invoice
1. Open the posted invoice from Test 6
2. Try to edit the invoice line and change Tax 2
3. **Expected**: Error message "You cannot modify taxes... because the invoice is already posted"
4. Try to change Tax 1
5. **Expected**: Same error

### Test 8: Prevent duplicate tax selection
1. Create a new invoice
2. On a line, select the same tax (e.g., 15%) in BOTH Taxes column (Tax 1) and Tax 2 column
3. **Expected**:
   - Onchange warning appears immediately in UI: "Tax '15%' is already selected in Tax 2 column. It has been removed from Tax 1."
   - Or on save, validation error: "tax cannot be selected in both Tax 1 and Tax 2 columns"

**Important**: Constraint checks `tax_ids` vs `tax2_ids`.

### Test 9: PDF Report verification
1. For each test invoice, print the PDF report
2. **Expected**:
   - All lines show Tax 2 column
   - Lines with Tax 2 show the tax name/description
   - Lines without Tax 2 show empty cell
   - Invoices without any Tax 2 still print correctly (column may be empty)
   - Standard tax totals block shows correct values

### Test 10: Tax 2 preserved when changing Tax 1
1. Create invoice with line having both Tax 1 (15%) and Tax 2 (2.1%)
2. Save draft
3. Change Taxes column (Tax 1) to a different tax (e.g., 5%)
4. **Expected**:
   - Tax 2 column still shows 2.1%
   - Line taxes: Tax 1 = 5% + Tax 2 = 2.1%
   - Total updates correctly

**Design Verification**: Changing `tax_ids` should not affect `tax2_ids`.

### Test 11: Remove Tax 2 keeps Tax 1
1. Create invoice with line having Tax 1 (15%) + Tax 2 (2.1%)
2. Save draft
3. Clear the Tax 2 column
4. **Expected**:
   - Tax 2 column is now empty
   - Taxes column (Tax 1) still shows 15%
   - `tax_ids` unchanged (still 15%)
   - Total = 115 (100 + 15%)

**Design Verification**: Clearing `tax2_ids` does not affect `tax_ids`.

## Regression Tests

### Test R1: Existing invoices without module
1. Open existing invoices created before module installation
2. **Expected**: They display and calculate correctly
3. Try to edit and save (without changing taxes)
4. **Expected**: No errors

### Test R2: Studio customizations preserved
1. If Studio customizations exist on invoice PDF
2. Print invoice with Tax 2
3. **Expected**: Studio customizations are still present

## Sign-off Checklist
- [ ] All Test 1-11 passed
- [ ] Regression tests passed
- [ ] Journal entries verified with accountant
- [ ] PDF layout approved by customer
- [ ] Posted invoice protection working
- [ ] Duplicate tax prevention working
