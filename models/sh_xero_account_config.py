# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class XeroAccountConfig(models.Model):
    _name = 'sh.xero.account.config'
    _description = 'Helps you to map odoo accounts with the xero'
    _order = 'id desc'

    sh_xero_acc_id = fields.Many2one('account.account', string='Xero Account')
    sh_odoo_acc_id = fields.Many2one('account.account', string='Odoo Account')
