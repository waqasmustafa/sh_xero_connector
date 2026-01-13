# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class QuotationLineXero(models.Model):
    _inherit = 'sale.order.line'

    sh_xero_line_id = fields.Char("Xero Orderline", copy=False)


class QuotationXero(models.Model):
    _inherit = 'sale.order'

    sh_xero_quotation_id = fields.Char("Xero Quotation", copy=False)
    sh_xero_quote_number = fields.Char("XERO Quote Number", copy=False)
    sh_xero_config = fields.Many2one(
        'sh.xero.configuration', string="Xero Config", copy=False)
    failure_reason = fields.Char("Failure Reason", copy=False)

    def export_xero_orders(self):
        active_sale_order_ids = self.env['sale.order'].browse(
            self.env.context.get('active_ids'))
        domain = [('company_id', '=', self.env.user.company_id.id)]
        find_config = self.env['sh.xero.configuration'].search(domain)
        return find_config.quotation_export(active_sale_order_ids)
