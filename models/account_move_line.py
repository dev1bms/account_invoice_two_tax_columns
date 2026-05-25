# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # =====================================================================
    # Field
    # =====================================================================
    tax2_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='account_move_line_tax2_rel',
        column1='move_line_id',
        column2='tax_id',
        string='Tax 2',
        domain="[('type_tax_use','=', parent_type_tax_use_filter),"
               " ('company_id','=', company_id)]",
        check_company=True,
        help="Secondary tax applied to this invoice line in addition to the "
             "standard Taxes field. Computed by Odoo as a real account.tax.",
    )

    parent_type_tax_use_filter = fields.Char(
        compute='_compute_parent_type_tax_use_filter', store=False,
    )

    @api.depends('move_id.move_type')
    def _compute_parent_type_tax_use_filter(self):
        for line in self:
            mt = line.move_id.move_type or 'out_invoice'
            if mt in ('out_invoice', 'out_refund', 'out_receipt'):
                line.parent_type_tax_use_filter = 'sale'
            elif mt in ('in_invoice', 'in_refund', 'in_receipt'):
                line.parent_type_tax_use_filter = 'purchase'
            else:
                line.parent_type_tax_use_filter = 'none'

    # =====================================================================
    # Constraints
    # =====================================================================
    @api.constrains('tax_ids', 'tax2_ids')
    def _check_no_duplicate_tax2(self):
        for line in self:
            dup = line.tax_ids & line.tax2_ids
            if dup:
                raise ValidationError(_(
                    "The tax '%s' cannot be selected in both the Taxes column "
                    "and the Tax 2 column on the same invoice line."
                ) % dup[0].display_name)

    # =====================================================================
    # Onchange: mark line for tax recomputation when Tax 2 changes
    # =====================================================================
    # _onchange_mark_recompute_taxes (native) watches `tax_ids` and sets
    # recompute_tax_line = True. Without an equivalent for tax2_ids the move's
    # _recompute_dynamic_lines() refuses to call _recompute_tax_lines() and
    # therefore no tax journal lines are created for Tax 2.
    # =====================================================================
    @api.onchange('tax2_ids')
    def _onchange_tax2_ids(self):
        for line in self:
            dup = line.tax2_ids & line.tax_ids
            if dup:
                line.tax2_ids = line.tax2_ids - dup
                return {
                    'warning': {
                        'title': _('Duplicate Tax'),
                        'message': _(
                            "Tax '%s' is already selected in the Taxes column. "
                            "It has been removed from Tax 2."
                        ) % dup[0].display_name,
                    }
                }
            # Mark the line so that _recompute_dynamic_lines triggers
            # _recompute_tax_lines on the parent move (same mechanism Odoo
            # uses when the native tax_ids field changes).
            if not line.tax_repartition_line_id:
                line.recompute_tax_line = True

    # =====================================================================
    # Line-level price_total: include Tax 2 so the line subtotal/total
    # displayed in the row reflects both taxes.
    # =====================================================================
    def _get_price_total_and_subtotal(self, price_unit=None, quantity=None,
                                      discount=None, currency=None,
                                      product=None, partner=None, taxes=None,
                                      move_type=None):
        self.ensure_one()
        effective = taxes if taxes is not None else self.tax_ids
        if self.tax2_ids:
            effective = effective | self.tax2_ids
        return super(AccountMoveLine, self)._get_price_total_and_subtotal(
            price_unit=price_unit, quantity=quantity, discount=discount,
            currency=currency, product=product, partner=partner,
            taxes=effective, move_type=move_type,
        )

    # =====================================================================
    # Posted invoice protection: forbid changing Tax 2 after post.
    # =====================================================================
    def write(self, vals):
        if 'tax2_ids' in vals:
            for line in self:
                if line.move_id and line.move_id.state == 'posted':
                    raise UserError(_(
                        "You cannot modify Tax 2 on line '%s' because the "
                        "invoice is already posted."
                    ) % (line.name or _('New')))
        return super().write(vals)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # =====================================================================
    # CORE FIX: override _recompute_tax_lines so Tax 2 produces real tax
    # journal lines (lines with tax_line_id set). _compute_amount sums those
    # lines into amount_tax / amount_total, and the totals area on the form
    # reads amount_by_group from the same tax lines.
    #
    # Strategy (verified against odoo/14.0 account/models/account_move.py):
    #   * For each base line that has tax2_ids, temporarily set
    #     line.tax_ids = tax_ids | tax2_ids via direct field assignment.
    #     - In draft/onchange mode (NewId records) this only updates the
    #       in-memory cache, so no DB pollution happens at all.
    #     - In persisted mode this writes to the DB, and we restore it in a
    #       try/finally so the final stored value is again Tax 1 only.
    #   * Call super(). Odoo iterates `self.line_ids`, sees the merged
    #     tax_ids, calls account.tax.compute_all() and creates the proper
    #     tax_repartition_line records (one per tax).
    #   * In `finally`, restore the original tax_ids of each affected line.
    #   * A context flag prevents re-entry / recursion.
    # =====================================================================

    def _recompute_tax_lines(self, *args, **kwargs):
        if self.env.context.get('_tax2_merge_in_progress'):
            return super()._recompute_tax_lines(*args, **kwargs)

        # Collect lines that have a Tax 2 to merge.
        affected = self.line_ids.filtered(
            lambda l: not l.tax_repartition_line_id and l.tax2_ids
        )
        backup = {l.id: l.tax_ids for l in affected}

        try:
            for line in affected:
                merged = line.tax_ids | line.tax2_ids
                # Direct field assignment: works for NewId (in-memory cache)
                # and for persisted records. Wrapped in a context flag so the
                # downstream onchanges do not re-enter this method.
                line.with_context(_tax2_merge_in_progress=True).tax_ids = merged
                _logger.debug(
                    "tax2_merge: line %s tax_ids %s -> %s (added %s)",
                    line.id, backup[line.id].mapped('name'),
                    merged.mapped('name'), line.tax2_ids.mapped('name'),
                )

            result = super(
                AccountMove,
                self.with_context(_tax2_merge_in_progress=True),
            )._recompute_tax_lines(*args, **kwargs)
        finally:
            # Restore the original Tax 1 only state on each affected line.
            for line in affected:
                if line.exists():
                    line.with_context(
                        _tax2_merge_in_progress=True
                    ).tax_ids = backup[line.id]

        return result
