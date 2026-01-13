# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class PurchaseXero(models.Model):
    _inherit = 'purchase.order.line'

    sh_xero_purchase_line_id = fields.Char("Xero PurchaseLine", copy=False)


class PurchaseLineXero(models.Model):
    _inherit = 'purchase.order'

    sh_xero_purchase_id = fields.Char("Xero Purchase Id", copy=False)
    sh_xero_config = fields.Many2one(
        'sh.xero.configuration', string="Xero Config", copy=False)
    sh_xero_purchase_number = fields.Char(
        "XERO Purchase Order Number", copy=False)
    failure_reasons = fields.Char("Failure Reason", copy=False)

    def export_xero_purchase_orders(self):
        active_purchase_ids = self.env['purchase.order'].browse(
            self.env.context.get('active_ids'))
        domain = [('company_id', '=', self.env.user.company_id.id)]
        find_config = self.env['sh.xero.configuration'].search(domain)
        return find_config.purchase_export(active_purchase_ids)
