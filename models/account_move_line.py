# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # ==========================================================================
    # ROBUST DESIGN: Effective Tax Computation with UI Separation
    # ==========================================================================
    # - tax_ids: Native Odoo field = Tax 1 (visible in UI, standard behavior)
    # - tax2_ids: Custom field = Tax 2 (visible in UI, separate column)
    #
    # CRITICAL: For Odoo to calculate Tax 2 in totals/journal entries, we must
    # temporarily include tax2_ids in tax_ids during computation.
    #
    # Implementation:
    # - _prepare_tax_line_update(): Temporarily merge tax2_ids into tax_ids
    # - After computation: Restore tax_ids to contain only Tax 1
    # - UI/PDF: Display tax_ids (Tax 1) and tax2_ids (Tax 2) separately
    # - Backend: Computes with union of both for correct totals
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
        help="Optional secondary tax for this line. Computed together with Tax 1 "
             "but displayed separately in UI and PDF.",
    )

    # Store original tax_ids (Tax 1 only) to restore after computation
    # This is a technical field, not stored in database
    _tax1_only_cache = fields.Many2many(
        comodel_name='account.tax',
        relation='account_move_line_tax1_cache_rel',
        column1='move_line_id',
        column2='tax_id',
        store=False,
        copy=False,
        string='Tax 1 Cache (Technical)',
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
    # Robust Tax Computation: Temporary Merge for Calculation
    # ------------------------------------------------------------------

    def _get_effective_taxes_for_computation(self):
        """Return combined taxes for computation: tax_ids + tax2_ids.

        This is used to temporarily set tax_ids to the full set before
        Odoo's tax computation runs, ensuring Tax 2 is included in totals.
        """
        self.ensure_one()
        tax1_only = self.tax_ids
        tax2_only = self.tax2_ids
        if tax2_only:
            return (tax1_only | tax2_only).sorted(key=lambda t: t.sequence)
        return tax1_only

    def _prepare_tax_line_update(self):
        """Override to include Tax 2 in tax computation.

        CRITICAL METHOD: This is called by Odoo during _recompute_tax_lines()
        to determine which taxes apply to each line.

        Strategy:
        1. Temporarily merge tax2_ids into tax_ids
        2. Call super() to let Odoo compute with both taxes
        3. Restore tax_ids to original Tax 1 only (for clean UI display)
        """
        # Store current Tax 1 only taxes (before any merge)
        original_tax1_only = self.tax_ids

        # If this line has Tax 2, temporarily merge into tax_ids for computation
        if self.tax2_ids:
            effective_taxes = self._get_effective_taxes_for_computation()
            # Use sudo to bypass any potential access restrictions
            self.sudo().write({'tax_ids': [(6, 0, effective_taxes.ids)]})

        # Call super to compute with merged taxes
        result = super(AccountMoveLine, self)._prepare_tax_line_update()

        # CRITICAL: Restore tax_ids to contain only Tax 1 (for UI cleanliness)
        # We use a context flag to avoid recursion
        if self.tax2_ids and not self.env.context.get('skip_tax_restore'):
            self.with_context(skip_tax_restore=True).sudo().write({
                'tax_ids': [(6, 0, original_tax1_only.ids)]
            })

        return result

    def _get_price_total_and_subtotal(self, price_unit=None, quantity=None, discount=None, currency=None, product=None, partner=None, taxes=None, move_type=None):
        """Override price computation to include Tax 2.

        This ensures line subtotals include both Tax 1 and Tax 2.
        """
        self.ensure_one()
        # If taxes not provided, use effective taxes (Tax 1 + Tax 2)
        if taxes is None and self.tax2_ids:
            taxes = self._get_effective_taxes_for_computation()
        return super(AccountMoveLine, self)._get_price_total_and_subtotal(
            price_unit=price_unit, quantity=quantity, discount=discount,
            currency=currency, product=product, partner=partner,
            taxes=taxes, move_type=move_type
        )

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
            # Trigger tax recomputation by temporarily setting context flag
            # The actual computation happens via _recompute_tax_lines on the move

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

        # If Tax 2 is being modified, trigger tax recomputation on the move
        if 'tax2_ids' in vals:
            result = super().write(vals)
            # Trigger tax recomputation on the parent move
            for line in self:
                if line.move_id and line.move_id.state == 'draft':
                    line.move_id._recompute_dynamic_lines(True, False)
            return result

        return super().write(vals)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _recompute_tax_lines(self, **kwargs):
        """Override tax line recomputation to handle Tax 2 properly.

        This ensures Tax 2 is included in the tax calculation while keeping
        tax_ids clean (containing only Tax 1) for UI display.
        """
        # Store original tax_ids for all lines before computation
        original_taxes = {}
        for line in self.line_ids.filtered(lambda l: l.tax2_ids):
            original_taxes[line.id] = line.tax_ids.ids
            # Temporarily merge tax2_ids into tax_ids for computation
            effective = (line.tax_ids | line.tax2_ids).sorted(key=lambda t: t.sequence)
            line.sudo().write({'tax_ids': [(6, 0, effective.ids)]})

        # Call super to compute with merged taxes - pass all kwargs
        result = super(AccountMove, self)._recompute_tax_lines(**kwargs)

        # Restore original tax_ids (Tax 1 only) for clean UI display
        for line_id, tax_ids in original_taxes.items():
            line = self.env['account.move.line'].browse(line_id)
            if line.exists():
                line.sudo().write({'tax_ids': [(6, 0, tax_ids)]})

        return result
