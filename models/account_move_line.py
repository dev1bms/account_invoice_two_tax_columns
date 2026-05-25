# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # ==========================================================================
    # DESIGN: Two UI fields (tax1_ids, tax2_ids) + One effective field (tax_ids)
    # ==========================================================================
    # - tax1_ids: UI field for "Tax 1" column. Users select normal taxes here.
    # - tax2_ids: UI field for "Tax 2" column. Users select extra taxes here.
    # - tax_ids: Native Odoo field, HIDDEN from UI. Contains merge of tax1_ids
    #            + tax2_ids. This is what Odoo's tax engine uses for computation.
    #
    # Flow: tax1_ids + tax2_ids (UI) -> _sync_to_tax_ids() -> tax_ids (effective)
    # ==========================================================================

    # Tax 1 column - UI only. Mirrors native tax_ids behavior for display.
    tax1_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='account_move_line_tax1_rel',
        column1='move_line_id',
        column2='tax_id',
        string='Tax 1',
        domain="[('type_tax_use','=', parent_type_tax_use_filter), "
               "('company_id','=', company_id)]",
        check_company=True,
        help="Primary taxes for this line. These are merged with Tax 2 into "
             "the standard Taxes field used by Odoo's accounting engine.",
    )

    # Tax 2 column - UI only. Extra tax column separate from Tax 1.
    tax2_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='account_move_line_tax2_rel',
        column1='move_line_id',
        column2='tax_id',
        string='Tax 2',
        domain="[('type_tax_use','=', parent_type_tax_use_filter), "
               "('company_id','=', company_id)]",
        check_company=True,
        help="Optional secondary tax for this line. These are merged with "
             "Tax 1 into the standard Taxes field used by Odoo's accounting engine.",
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
    @api.constrains('tax1_ids', 'tax2_ids')
    def _check_no_duplicate_taxes(self):
        """Prevent the same tax appearing in both Tax 1 and Tax 2 columns."""
        for line in self:
            duplicates = line.tax1_ids & line.tax2_ids
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
    # Core Sync Logic: Merge tax1_ids + tax2_ids -> tax_ids (effective)
    # ------------------------------------------------------------------
    def _get_effective_tax_ids(self):
        """Return combined tax1_ids + tax2_ids for effective tax computation."""
        self.ensure_one()
        return (self.tax1_ids | self.tax2_ids).sorted(key=lambda t: t.sequence)

    def _sync_to_tax_ids(self):
        """Sync tax1_ids + tax2_ids into native tax_ids field.

        This is the critical bridge: Odoo's tax engine only reads tax_ids,
        so we must keep it in sync with our two UI columns.
        """
        for line in self:
            # Never modify posted invoices
            if line.move_id and line.move_id.state == 'posted':
                continue
            effective_taxes = line._get_effective_tax_ids()
            current_tax_ids = line.tax_ids
            if set(effective_taxes.ids) != set(current_tax_ids.ids):
                # Use super write to avoid recursion
                super(AccountMoveLine, line).write({
                    'tax_ids': [(6, 0, effective_taxes.ids)],
                })

    # ------------------------------------------------------------------
    # Onchange Handlers (Form UI live updates)
    # ------------------------------------------------------------------
    @api.onchange('tax1_ids')
    def _onchange_tax1_ids(self):
        """When Tax 1 changes, update effective tax_ids.

        Also prevent selecting a tax in Tax 1 that is already in Tax 2.
        """
        for line in self:
            # Prevent duplicates between columns
            duplicates = line.tax1_ids & line.tax2_ids
            if duplicates:
                # Remove duplicate from tax1_ids
                line.tax1_ids = line.tax1_ids - duplicates
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
            # Sync to effective tax_ids
            effective = (line.tax1_ids | line.tax2_ids)
            if set(line.tax_ids.ids) != set(effective.ids):
                line.tax_ids = effective

    @api.onchange('tax2_ids')
    def _onchange_tax2_ids(self):
        """When Tax 2 changes, update effective tax_ids.

        Also prevent selecting a tax in Tax 2 that is already in Tax 1.
        """
        for line in self:
            # Prevent duplicates between columns
            duplicates = line.tax2_ids & line.tax1_ids
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
            # Sync to effective tax_ids
            effective = (line.tax1_ids | line.tax2_ids)
            if set(line.tax_ids.ids) != set(effective.ids):
                line.tax_ids = effective

    # ------------------------------------------------------------------
    # CRUD Overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        # Handle tax1_ids/tax2_ids in vals - map to tax_ids for creation
        for vals in vals_list:
            if 'tax1_ids' in vals or 'tax2_ids' in vals:
                # Combine both into tax_ids for native Odoo processing
                tax1_ids = []
                tax2_ids = []
                if 'tax1_ids' in vals:
                    tax1_cmd = vals.pop('tax1_ids')
                    tax1_ids = self._extract_ids_from_command(tax1_cmd)
                if 'tax2_ids' in vals:
                    tax2_cmd = vals.pop('tax2_ids')
                    tax2_ids = self._extract_ids_from_command(tax2_cmd)
                combined = list(set(tax1_ids + tax2_ids))
                if combined:
                    vals['tax_ids'] = [(6, 0, combined)]
        lines = super().create(vals_list)
        # After creation, sync to ensure consistency
        lines._sync_to_tax_ids()
        return lines

    def write(self, vals):
        # Check posted invoice protection for tax changes
        if any(k in vals for k in ('tax1_ids', 'tax2_ids', 'tax_ids')):
            self._check_move_not_posted()
        # Handle tax1_ids/tax2_ids writes
        if 'tax1_ids' in vals or 'tax2_ids' in vals:
            # Get current values for lines being modified
            previous_tax1 = {l.id: l.tax1_ids for l in self} if 'tax1_ids' in vals else {}
            previous_tax2 = {l.id: l.tax2_ids for l in self} if 'tax2_ids' in vals else {}
            # Pop our custom fields - we'll handle tax_ids manually
            tax1_vals = vals.pop('tax1_ids', None)
            tax2_vals = vals.pop('tax2_ids', None)
            # Apply the write for our custom fields first (to stored computed fields)
            res = super().write(vals) if vals else True
            if tax1_vals is not None:
                res = super(AccountMoveLine, self).write({'tax1_ids': tax1_vals}) and res
            if tax2_vals is not None:
                res = super(AccountMoveLine, self).write({'tax2_ids': tax2_vals}) and res
            # Now sync effective tax_ids
            self._sync_to_tax_ids()
            return res
        return super().write(vals)

    @staticmethod
    def _extract_ids_from_command(cmd):
        """Extract tax IDs from Odoo x2m command format."""
        if not cmd:
            return []
        ids = []
        for item in cmd:
            if isinstance(item, tuple) or isinstance(item, list):
                if item[0] == 6:  # (6, 0, [ids])
                    ids.extend(item[2] if item[2] else [])
                elif item[0] == 4:  # (4, id)
                    ids.append(item[1])
        return ids

