# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class XeroProductVariant(models.Model):
    _inherit = 'product.product'

    failure_reason = fields.Char("Failure Reason", copy=False)
    sh_xero_product_id = fields.Char("Xero Product ID", copy=False)
    sh_xero_config = fields.Many2one('sh.xero.configuration', string="Xero Config", copy=False)
