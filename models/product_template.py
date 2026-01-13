# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class ProductXero(models.Model):
    _inherit = 'product.template'

    failure_reasons = fields.Char("Failure Reason", copy=False)
    sh_xero_product_id = fields.Char("Xero Products", copy=False)
    sh_xero_config = fields.Many2one(
        'sh.xero.configuration', string="Xero Config", copy=False)

    def export_xero_product(self):
        active_product_ids = self.env['product.template'].browse(
            self.env.context.get('active_ids'))
        domain = [('company_id', '=', self.env.user.company_id.id)]
        find_config = self.env['sh.xero.configuration'].search(domain)
        return find_config.products_export(active_product_ids)
