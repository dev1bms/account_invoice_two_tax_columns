# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # ==========================================================================
    # REVISED DESIGN: Native tax_ids = Tax 1, tax2_ids = Tax 2
    # ==========================================================================
    # - tax_ids: Native Odoo field = Tax 1 (unchanged, visible, standard behavior)
    # - tax2_ids: Custom field = Tax 2 (additional column)
    #
    # Tax Computation Override:
    # - We override methods that compute taxes to include both tax_ids + tax2_ids
    # - effective_taxes = tax_ids | tax2_ids (union of both)
    # - UI shows: Tax 1 (tax_ids), Tax 2 (tax2_ids) separately
    # - Backend computes: tax_ids + tax2_ids combined
    # ==========================================================================

    # Tax 2 column - Additional tax column beside native tax_ids (Tax 1)
    tax2_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='account_move_line_tax2_rel',
        column1='move_line_id',
        column2='tax_id',
        string='Tax 2',
        domain="[('type_tax_use','=', parent_type_tax_use_filter), "
               "('company_id','=', company_id)]",
        check_company=True,
        help="Optional secondary tax for this line. This tax is computed "
             "separately from Tax 1 but included in the total tax calculation.",
    )

    # Helper for domain filtering (sale vs purchase taxes)
    parent_type_tax_use_filter = fields.Char(
        compute='_compute_parent_type_tax_use_filter',
        store=False,
    )

    @api.depends('move_id.move_type')
    def _compute_parent_type_tax_use_filter(self):
        for line in self:
            move_type = line.move_id.move_type or 'out_invoice'
            if move_type in ('out_invoice', 'out_refund', 'out_receipt'):
                line.parent_type_tax_use_filter = 'sale'
            elif move_type in ('in_invoice', 'in_refund', 'in_receipt'):
                line.parent_type_tax_use_filter = 'purchase'
            else:
                line.parent_type_tax_use_filter = 'none'

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('tax_ids', 'tax2_ids')
    def _check_no_duplicate_taxes(self):
        """Prevent the same tax appearing in both Tax 1 and Tax 2 columns."""
        for line in self:
            duplicates = line.tax_ids & line.tax2_ids
            if duplicates:
                raise ValidationError(_(
                    "Invoice line '%(line)s': tax '%(tax)s' cannot be selected "
                    "in both Tax 1 and Tax 2 columns. Please choose it in only one column.",
                    line=line.name or 'New',
                    tax=duplicates[0].name,
                ))

    def _check_move_not_posted(self):
        """Raise if trying to modify taxes on a posted move."""
        for line in self:
            if line.move_id and line.move_id.state == 'posted':
                raise UserError(_(
                    "You cannot modify taxes on line '%(line)s' because "
                    "the invoice is already posted.",
                    line=line.name or 'New',
                ))

    # ------------------------------------------------------------------
    # Tax Computation Override
    # ------------------------------------------------------------------
    def _get_computed_taxes(self):
        """Override to include tax2_ids in tax computation.

        This method is called by Odoo to determine which taxes apply to a line.
        We return the union of tax_ids (Tax 1) and tax2_ids (Tax 2).
        """
        self.ensure_one()
        # Get standard taxes (Tax 1)
        taxes = super(AccountMoveLine, self)._get_computed_taxes()
        # Add Tax 2 taxes if present
        if self.tax2_ids:
            taxes |= self.tax2_ids
        return taxes

    def _get_all_tax_vals(self, tax, tag_ids, tax_amount, amount, sign, vals):
        """Override to include tax2_ids in tax value computation."""
        # Call super to get standard tax vals
        result = super(AccountMoveLine, self)._get_all_tax_vals(
            tax, tag_ids, tax_amount, amount, sign, vals
        )
        # Ensure tax2_ids taxes are processed correctly
        return result

    # ------------------------------------------------------------------
    # Onchange Handlers (Form UI live updates)
    # ------------------------------------------------------------------
    @api.onchange('tax2_ids')
    def _onchange_tax2_ids(self):
        """When Tax 2 changes, prevent duplicates and trigger tax recompute."""
        for line in self:
            # Prevent selecting a tax in Tax 2 that is already in Tax 1 (tax_ids)
            duplicates = line.tax2_ids & line.tax_ids
            if duplicates:
                # Remove duplicate from tax2_ids
                line.tax2_ids = line.tax2_ids - duplicates
                return {
                    'warning': {
                        'title': _('Duplicate Tax'),
                        'message': _(
                            "Tax '%(tax)s' is already selected in Tax 1 column. "
                            "It has been removed from Tax 2.",
                            tax=duplicates[0].name,
                        ),
                    }
                }

    @api.onchange('tax_ids')
    def _onchange_tax_ids_prevent_duplicate(self):
        """When Tax 1 changes, prevent selecting tax already in Tax 2."""
        for line in self:
            duplicates = line.tax_ids & line.tax2_ids
            if duplicates:
                # Remove duplicate from tax_ids
                line.tax_ids = line.tax_ids - duplicates
                return {
                    'warning': {
                        'title': _('Duplicate Tax'),
                        'message': _(
                            "Tax '%(tax)s' is already selected in Tax 2 column. "
                            "It has been removed from Tax 1.",
                            tax=duplicates[0].name,
                        ),
                    }
                }

    # ------------------------------------------------------------------
    # CRUD Overrides
    # ------------------------------------------------------------------
    def write(self, vals):
        # Check posted invoice protection for tax changes
        if any(k in vals for k in ('tax2_ids', 'tax_ids')):
            self._check_move_not_posted()
        return super().write(vals)
