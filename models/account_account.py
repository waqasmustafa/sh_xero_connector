# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class AccountXero(models.Model):
    _inherit = 'account.account'

    sh_xero_account_id = fields.Char("Xero Account", copy=False)
    failure_reasons = fields.Char("Failure Reason", copy=False)
    sh_xero_config = fields.Many2one('sh.xero.configuration', copy=False)

    def export_xero_accounts(self):
        active_account_ids = self.env['account.account'].browse(
            self.env.context.get('active_ids'))
        find_config = self.env['sh.xero.configuration'].search([
            ('company_id', '=', self.env.user.company_id.id)])
        if not find_config:
            return
        return find_config.account_export(active_account_ids)
