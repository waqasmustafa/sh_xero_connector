# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class TaxXero(models.Model):
    _inherit = 'account.tax'

    xero_tax_type = fields.Char("XERO Tax Type", copy=False)
    sh_xero_config = fields.Many2one('sh.xero.configuration', copy=False)
    failure_reason = fields.Char("Failure Reason", copy=False)

    def export_xero_tax(self):
        active_tax_ids = self.env['account.tax'].browse(self.env.context.get('active_ids'))
        find_config =  self.env['sh.xero.configuration'].search([
            ('company_id', '=', self.env.user.company_id.id)])
        if not (find_config or active_tax_ids):
            return
        return find_config.wizard_tax_export(active_tax_ids)
