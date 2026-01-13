# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class SalesforceLogger(models.Model):
    _name = 'sh.xero.log'
    _description = 'Helps you to maintain the activity done'
    _order = 'id desc'

    name = fields.Char("Name")
    error = fields.Char("Message")
    datetime = fields.Datetime("Date & Time")
    sh_xero_id = fields.Many2one('sh.xero.configuration')
    state = fields.Selection([('success', 'Success'), ('error', 'Failed')])
    type_ = fields.Selection([
        ('contact', 'Contacts'),
        ('journal', 'Manual Journal'),
        ('refund', 'Vendor Refund'),
        ('product', 'Product'),
        ('account', 'Account'),
        ('bill', 'Vendor Bills'),
        ('quotes', 'Quotation'),
        ('tax', 'Tax'),
        ('purchase', 'Purchase Orders'),
        ('credit_note', 'Credit Note'),
        ('invoice', 'Invoice'),
        ('payment', 'Payments')
    ], string='Type')
    failed_list = fields.Char('Failed List')

    # -----------------------------------------------
    #  Get the view to return
    # -----------------------------------------------

    def process_view(self, name, model, tree_view_id):
        if not self.failed_list:
            return False
        view_id = self.env.ref(f'sh_xero_connector.{tree_view_id}').id
        id_list = [int(str_id) for str_id in self.failed_list.split(',')]
        return {
            "type": "ir.actions.act_window",
            "name": f"Unsynced {name}",
            "view_mode": "tree,form",
            "res_model": model,
            "domain": [('id', 'in', id_list)],
            "views": [(view_id, "list"), (False, "form")],
            "context": {'create': False, 'delete': False}
        }

    # -----------------------------------------------
    #  Return the view
    # -----------------------------------------------

    def send_logger(self):
        if self.type_ == 'purchase':
            return self.process_view('Purchase Orders', 'purchase.order', 'xero_purchase_order_failed_tree')
        if self.type_ in ('refund', 'bill', 'credit_note', 'invoice'):
            return self.process_view(self.type_.capitalize(), 'account.move', 'xero_invoice_failed_tree')
        if self.type_ == 'quotes':
            return self.process_view('Quoatation', 'sale.order', 'xero_quotation_failed_tree')
        if self.type_ == 'contact':
            return self.process_view('Contact', 'res.partner', 'xero_res_partner_failed_tree')
        if self.type_ == 'account':
            return self.process_view('Account', 'account.account', 'xero_account_failed_tree')
        if self.type_ == 'tax':
            return self.process_view('Tax', 'account.tax', 'xero_tax_failed_tree')
        if self.type_ == 'product':
            return self.process_view('Accounts', 'product.product', 'xero_products_failed_tree')
        if self.type_ == 'journal':
            return self.process_view('Journal', 'account.move', 'xero_invoice_failed_tree')
        return False
