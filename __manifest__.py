{
    'name': 'Account Invoice Two Tax Columns',
    'version': '14.0.1.0.0',
    'summary': 'Adds a second tax column (Tax 2) on customer invoice lines and PDF report.',
    'description': """
Two Tax Columns on Customer Invoices
====================================
Adds an extra Many2many field ``tax2_ids`` on ``account.move.line`` so users can
select a second tax per line independently from the primary tax. Both selections
are merged into the standard ``tax_ids`` field used by Odoo's native tax engine,
so accounting totals, journal entries and tax reports stay correct.

The standard customer invoice PDF (``account.report_invoice_document``) is
extended with a second column showing Tax 2 per line. Lines without Tax 2 are
shown empty; invoices that have no Tax 2 at all stay visually close to the
original report.
""",
    'author': 'Alnahda',
    'category': 'Accounting/Accounting',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'views/account_move_views.xml',
        'reports/report_invoice_document.xml',
    ],
    'demo': [],
    'test': [
        'tests/test_invoice_two_tax_columns.py',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
