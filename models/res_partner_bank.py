from odoo import api, models


class ResPartnerBank(models.Model):
    """Extend res.partner.bank to auto-sync bank account changes
    back to all workforce worker cards linked to the same contact.

    This handles the common scenario where a worker starts working
    before registering their bank account — once the bank account
    is added (or updated) on the contact, all existing worker cards
    are automatically updated so printed summaries always show
    the latest bank details.
    """
    _inherit = 'res.partner.bank'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for bank in records:
            if bank.partner_id:
                bank._sync_to_worker_cards()
        return records

    def write(self, vals):
        res = super().write(vals)
        # If the account number or holder name changed, push to worker cards
        if 'acc_number' in vals or 'acc_holder_name' in vals:
            for bank in self:
                if bank.partner_id:
                    bank._sync_to_worker_cards()
        return res

    def _sync_to_worker_cards(self):
        """Push this bank account's details to all worker cards
        belonging to the same partner that currently have no
        account number (or have the old one)."""
        self.ensure_one()
        if not self.partner_id:
            return

        # Find all worker cards for this contact
        entries = self.env['budget.timesheet.entry'].search([
            ('partner_id', '=', self.partner_id.id),
        ])

        if not entries:
            return

        # Update worker cards that have no bank account, or whose
        # account number differs from this (latest) bank account.
        # We use the first bank account on the contact (sorted by id)
        # to stay consistent with the onchange logic.
        first_bank = self.env['res.partner.bank'].search([
            ('partner_id', '=', self.partner_id.id),
        ], limit=1, order='id asc')

        if not first_bank:
            return

        for entry in entries:
            if entry.account_number != first_bank.acc_number:
                entry.write({
                    'account_number': first_bank.acc_number,
                    'account_holder_name': (
                        first_bank.acc_holder_name
                        or entry.partner_id.name
                    ),
                })
