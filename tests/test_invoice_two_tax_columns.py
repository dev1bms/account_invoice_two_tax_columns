# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestInvoiceTwoTaxColumns(TransactionCase):
    """Test suite for Account Invoice Two Tax Columns module.

    Test scenarios:
    1. Line with Tax 1 only
    2. Line with Tax 2 only
    3. Line with Tax 1 + Tax 2
    4. Invoice without Tax 2
    5. Post invoice and verify journal entries include Tax 2
    6. Prevent modification of posted invoice taxes
    7. Prevent duplicate tax in both columns
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer',
            'is_company': True,
        })

        # Create test taxes (accountant would normally do this manually)
        cls.tax_15 = cls.env['account.tax'].create({
            'name': 'Tax 1 (15%)',
            'amount': 15,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'company_id': cls.company.id,
        })
        cls.tax_21 = cls.env['account.tax'].create({
            'name': 'Tax 2 (2.1%)',
            'amount': 2.1,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'company_id': cls.company.id,
        })
        cls.tax_5 = cls.env['account.tax'].create({
            'name': 'Tax Extra (5%)',
            'amount': 5,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'company_id': cls.company.id,
        })

        # Get/create product and accounts
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
            'type': 'service',
            'list_price': 100.0,
        })

        cls.account_receivable = cls.env['account.account'].search([
            ('company_id', '=', cls.company.id),
            ('account_type', '=', 'asset_receivable'),
        ], limit=1)
        cls.account_revenue = cls.env['account.account'].search([
            ('company_id', '=', cls.company.id),
            ('account_type', '=', 'income'),
        ], limit=1)

    def _create_invoice(self, line_taxes_list):
        """Create invoice with specified taxes per line.

        line_taxes_list: list of tuples (tax_ids, tax2_ids)
        - tax_ids: Tax 1 (native field)
        - tax2_ids: Tax 2 (custom field)
        """
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': '2024-01-01',
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'name': f'Line {i+1}',
                    'quantity': 1,
                    'price_unit': 100.0,
                    'tax_ids': [(6, 0, t1_ids.ids if t1_ids else [])],
                    'tax2_ids': [(6, 0, t2_ids.ids if t2_ids else [])],
                }) for i, (t1_ids, t2_ids) in enumerate(line_taxes_list)
            ],
        })
        return invoice

    def test_01_line_with_tax1_only(self):
        """Test: Line with Tax 1 (tax_ids) only (15%)."""
        invoice = self._create_invoice([(self.tax_15, None)])
        line = invoice.invoice_line_ids[0]

        # tax_ids should contain Tax 1
        self.assertIn(self.tax_15, line.tax_ids)
        # tax2_ids should be empty
        self.assertFalse(line.tax2_ids)
        # Verify computation: 100 + 15% = 115
        invoice.action_post()
        self.assertEqual(invoice.amount_total, 115.0)

    def test_02_line_with_tax2_only(self):
        """Test: Line with Tax 2 (tax2_ids) only (2.1%)."""
        invoice = self._create_invoice([(None, self.tax_21)])
        line = invoice.invoice_line_ids[0]

        # tax_ids (Tax 1) should be empty
        self.assertFalse(line.tax_ids)
        # tax2_ids should contain Tax 2
        self.assertIn(self.tax_21, line.tax2_ids)
        # Tax computation override should include tax2_ids
        computed_taxes = line._get_computed_taxes()
        self.assertIn(self.tax_21, computed_taxes)
        # Verify computation: 100 + 2.1% = 102.1
        invoice.action_post()
        self.assertAlmostEqual(invoice.amount_total, 102.1, places=1)

    def test_03_line_with_tax1_and_tax2(self):
        """Test: Line with Tax 1 (tax_ids: 15%) + Tax 2 (tax2_ids: 2.1%)."""
        invoice = self._create_invoice([(self.tax_15, self.tax_21)])
        line = invoice.invoice_line_ids[0]

        # tax_ids should have Tax 1
        self.assertIn(self.tax_15, line.tax_ids)
        # tax2_ids should have Tax 2
        self.assertIn(self.tax_21, line.tax2_ids)
        # Tax computation override should include both
        computed_taxes = line._get_computed_taxes()
        self.assertIn(self.tax_15, computed_taxes)
        self.assertIn(self.tax_21, computed_taxes)
        # Verify computation: 100 + 15% + 2.1% = 117.1
        invoice.action_post()
        self.assertAlmostEqual(invoice.amount_total, 117.1, places=1)

    def test_04_invoice_without_tax2(self):
        """Test: Invoice without Tax 2 on any line (only Tax 1 / tax_ids)."""
        invoice = self._create_invoice([
            (self.tax_15, None),
            (self.tax_5, None),
        ])

        # No line should have tax2_ids
        for line in invoice.invoice_line_ids:
            self.assertFalse(line.tax2_ids)

        # Verify totals: behaves like standard Odoo
        invoice.action_post()
        # Line 1: 100 + 15% = 115
        # Line 2: 100 + 5% = 105
        # Total = 220
        self.assertEqual(invoice.amount_total, 220.0)

    def test_05_mixed_invoice_lines(self):
        """Test: Mixed invoice with Tax 1 only, Tax 2 only, and both."""
        invoice = self._create_invoice([
            (self.tax_15, None),           # Line 1: Tax 1 only (tax_ids)
            (None, self.tax_21),           # Line 2: Tax 2 only (tax2_ids)
            (self.tax_15, self.tax_21),   # Line 3: Both
        ])

        lines = invoice.invoice_line_ids
        # Line 1: Tax 1 only
        self.assertIn(self.tax_15, lines[0].tax_ids)
        self.assertFalse(lines[0].tax2_ids)
        # Line 2: Tax 2 only
        self.assertFalse(lines[1].tax_ids)
        self.assertIn(self.tax_21, lines[1].tax2_ids)
        # Line 3: Both
        self.assertIn(self.tax_15, lines[2].tax_ids)
        self.assertIn(self.tax_21, lines[2].tax2_ids)

        # Post and verify totals
        invoice.action_post()
        # Line 1: 100 + 15% = 115
        # Line 2: 100 + 2.1% = 102.1
        # Line 3: 100 + 15% + 2.1% = 117.1
        # Total = 334.2
        self.assertAlmostEqual(invoice.amount_total, 334.2, places=1)

    def test_06_journal_entries_include_tax2(self):
        """Test: Posted invoice journal entries include Tax 2 amounts."""
        invoice = self._create_invoice([(self.tax_15, self.tax_21)])
        invoice.action_post()

        # Find tax lines in journal entry
        tax_lines = invoice.line_ids.filtered(lambda l: l.tax_line_id)
        tax_amounts = {line.tax_line_id: line.balance for line in tax_lines}

        # Should have both Tax 1 and Tax 2 lines
        self.assertIn(self.tax_15, tax_amounts)
        self.assertIn(self.tax_21, tax_amounts)
        # Tax amounts should be negative (liability)
        self.assertLess(tax_amounts[self.tax_15], 0)
        self.assertLess(tax_amounts[self.tax_21], 0)

    def test_07_prevent_modify_posted_invoice_taxes(self):
        """Test: Cannot modify taxes on posted invoice."""
        invoice = self._create_invoice([(self.tax_15, None)])
        invoice.action_post()

        line = invoice.invoice_line_ids[0]
        with self.assertRaises(UserError):
            line.write({'tax2_ids': [(6, 0, [self.tax_21.id])]})

    def test_08_prevent_duplicate_tax_in_both_columns(self):
        """Test: Same tax cannot be selected in both Tax 1 (tax_ids) and Tax 2 (tax2_ids)."""
        # Create with duplicate via ORM (should be caught by constraint)
        with self.assertRaises(ValidationError):
            self._create_invoice([(self.tax_15, self.tax_15)])

    def test_09_tax2_preserved_when_tax1_changes(self):
        """Test: Tax 2 is preserved when user changes Tax 1 (tax_ids)."""
        invoice = self._create_invoice([(self.tax_15, self.tax_21)])
        line = invoice.invoice_line_ids[0]

        # Change Tax 1 to different tax
        line.write({'tax_ids': [(6, 0, [self.tax_5.id])]})

        # Tax 2 should still be present
        self.assertIn(self.tax_21, line.tax2_ids)
        # New Tax 1 should be present
        self.assertIn(self.tax_5, line.tax_ids)

    def test_10_removing_tax2_keeps_tax1(self):
        """Test: Removing Tax 2 keeps Tax 1 unchanged."""
        invoice = self._create_invoice([(self.tax_15, self.tax_21)])
        line = invoice.invoice_line_ids[0]

        # Remove Tax 2
        line.write({'tax2_ids': [(5, 0, 0)]})

        # Tax 2 should be gone, Tax 1 should remain
        self.assertFalse(line.tax2_ids)
        self.assertIn(self.tax_15, line.tax_ids)

    def test_11_computed_taxes_include_both(self):
        """Test: _get_computed_taxes() returns union of tax_ids and tax2_ids."""
        invoice = self._create_invoice([(self.tax_15, self.tax_21)])
        line = invoice.invoice_line_ids[0]

        # Verify computed taxes include both
        computed_taxes = line._get_computed_taxes()
        self.assertIn(self.tax_15, computed_taxes)
        self.assertIn(self.tax_21, computed_taxes)
        self.assertEqual(len(computed_taxes), 2)
