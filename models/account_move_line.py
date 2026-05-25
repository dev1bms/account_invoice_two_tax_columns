# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # ==========================================================================
    # DESIGN (Odoo 14)
    # ==========================================================================
    # - tax_ids: Native Odoo field. Visible as the standard "Taxes" column.
    #            Behaves exactly like vanilla Odoo. Never polluted by Tax 2.
    # - tax2_ids: New Many2many to account.tax. Visible as the "Tax 2" column.
    #             Computed by Odoo together with tax_ids but stored separately.
    #
    # Computation hooks:
    # 1. _get_price_total_and_subtotal (line-level totals)
    #    -> we pass tax_ids | tax2_ids as the `taxes` argument so price_total
    #       includes both taxes.
    # 2. _recompute_tax_lines (move-level: generates tax journal lines)
    #    -> we temporarily expose tax2_ids alongside tax_ids during the super
    #       call, then restore. Uses an in-memory cache + try/finally to be
    #       robust against exceptions.
    # ==========================================================================

    tax2_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='account_move_line_tax2_rel',
        column1='move_line_id',
        column2='tax_id',
        string='Tax 2',
        domain="[('type_tax_use','=', parent_type_tax_use_filter),"
               " ('company_id','=', company_id)]",
        check_company=True,
        help="Optional secondary tax for this line. Computed by Odoo together "
             "with the standard Taxes (tax_ids) but displayed in its own column.",
    )

    # Helper to filter the tax selection by sale/purchase context.
    parent_type_tax_use_filter = fields.Char(
        compute='_compute_parent_type_tax_use_filter',
        store=False,
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

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('tax_ids', 'tax2_ids')
    def _check_no_duplicate_tax2(self):
        for line in self:
            dup = line.tax_ids & line.tax2_ids
            if dup:
                raise ValidationError(_(
                    "The tax '%s' cannot be selected in both the Taxes column "
                    "and the Tax 2 column on the same invoice line."
                ) % dup[0].display_name)

    # ------------------------------------------------------------------
    # Onchange: duplicate prevention + trigger recompute when Tax 2 changes
    # ------------------------------------------------------------------
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
                            "Tax '%s' is already in the Taxes column. "
                            "It has been removed from Tax 2."
                        ) % dup[0].display_name,
                    }
                }
            # Force re-evaluation of price_total/price_subtotal so the
            # in-form totals reflect Tax 2 immediately.
            line._onchange_price_subtotal()

    # ------------------------------------------------------------------
    # Line-level tax computation: include Tax 2 in price_total
    # ------------------------------------------------------------------
    def _get_price_total_and_subtotal(self, price_unit=None, quantity=None,
                                      discount=None, currency=None,
                                      product=None, partner=None, taxes=None,
                                      move_type=None):
        """Make price_total include Tax 2.

        Odoo passes `taxes=self.tax_ids` when called from internal helpers
        and may also pass it explicitly. In either case, we extend the
        recordset with self.tax2_ids before delegating to super.
        """
        self.ensure_one()
        if self.tax2_ids:
            effective = (taxes if taxes is not None else self.tax_ids) | self.tax2_ids
            return super(AccountMoveLine, self)._get_price_total_and_subtotal(
                price_unit=price_unit, quantity=quantity, discount=discount,
                currency=currency, product=product, partner=partner,
                taxes=effective, move_type=move_type,
            )
        return super(AccountMoveLine, self)._get_price_total_and_subtotal(
            price_unit=price_unit, quantity=quantity, discount=discount,
            currency=currency, product=product, partner=partner,
            taxes=taxes, move_type=move_type,
        )

    # ------------------------------------------------------------------
    # Posted invoice protection for Tax 2 modifications
    # ------------------------------------------------------------------
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

    # ==========================================================================
    # Move-level: ensure Tax 2 generates real account.tax journal lines.
    # ==========================================================================
    # _recompute_tax_lines is the method Odoo 14 uses to (re)build the dynamic
    # tax lines inside line_ids. It iterates self.line_ids and reads
    # line.tax_ids to call account.tax.compute_all() per line.
    #
    # We temporarily merge tax2_ids into tax_ids on a per-line basis, call
    # super, then restore. Uses a try/finally so the restore always runs.
    # Recursion is prevented via a context flag.
    # ==========================================================================

    def _recompute_tax_lines(self, *args, **kwargs):
        if self.env.context.get('_tax2_merge_in_progress'):
            return super()._recompute_tax_lines(*args, **kwargs)

        # Identify lines that have a Tax 2 and snapshot their original tax_ids.
        # We use direct SQL-free ORM writes with sudo to avoid permission issues
        # during the temporary merge.
        merged_lines = self.line_ids.filtered(lambda l: l.tax2_ids)
        original_by_id = {l.id: l.tax_ids.ids for l in merged_lines}

        try:
            # Step 1: merge tax2_ids into tax_ids on each affected line.
            for line in merged_lines:
                effective_ids = list(
                    set(line.tax_ids.ids) | set(line.tax2_ids.ids)
                )
                line.sudo().with_context(
                    _tax2_merge_in_progress=True
                ).write({'tax_ids': [(6, 0, effective_ids)]})

            # Step 2: let Odoo build the tax journal lines normally.
            result = super(
                AccountMove,
                self.with_context(_tax2_merge_in_progress=True),
            )._recompute_tax_lines(*args, **kwargs)
        finally:
            # Step 3: always restore tax_ids to its original Tax-1-only state.
            for line_id, original_ids in original_by_id.items():
                line = self.env['account.move.line'].browse(line_id)
                if line.exists():
                    line.sudo().with_context(
                        _tax2_merge_in_progress=True
                    ).write({'tax_ids': [(6, 0, original_ids)]})

        return result
