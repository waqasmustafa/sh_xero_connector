# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class PaymentXero(models.Model):
    _inherit = 'account.payment'

    sh_xero_payment_id = fields.Char('Xero Payment Id', copy=False)
    sh_xero_overpayment_id = fields.Char('Xero OverPayment Id', copy=False)
    sh_xero_prepayment_id = fields.Char('Xero PrePayment Id', copy=False)
    sh_xero_config = fields.Many2one('sh.xero.configuration', string="Xero Config", copy=False)

    def export_xero_payment(self):
        active_payment_ids = self.env['account.payment'].browse(
            self.env.context.get('active_ids'))
        domain = [('company_id', '=', self.env.user.company_id.id)]
        find_config = self.env['sh.xero.configuration'].search(domain)
        if not find_config:
            return
        return find_config._manage_payment(active_payment_ids)
