# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class XeroQueue(models.Model):
    _name = 'sh.xero.queue'
    _description = 'Helps you to add incoming req in queue'
    _order = 'id desc'

    queue_type = fields.Selection([
        ('quotation', 'Quotation'),
        ('purchase_order', 'Purchase Order'),
        ('invoice', 'Invoice'),
        ('bills', 'Bills'),
        ('credit_note', 'Credit Notes'),
        ('debit_note', 'Debit Notes'),
        ('journal', 'Journal')
    ], string='Queue Type')

    sh_id = fields.Char("Id")
    sh_queue_name = fields.Char("Name")
    queue_sync_date = fields.Datetime("Sync Date-Time")
    sh_current_config = fields.Many2one('sh.xero.configuration')
    sh_current_state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('error', 'Error')
    ], string="State")
    error = fields.Char('Error')

    def _error(self, error):
        self.write({
            'error': error,
            'sh_current_state': 'error'
        })

    def _done(self):
        self.write({
            'error': '',
            'sh_current_state': 'done'
        })

    def _draft(self):
        self.write({
            'error': '',
            'sh_current_state': 'draft'
        })

    def import_xero_manually(self):
        domain = [('user_id', '=', self.env.user.id)]
        find_config = self.env['sh.xero.configuration'].search(domain,limit=1)
        if not find_config:
            return
        active_queue_ids = self.env['sh.xero.queue'].browse(self.env.context.get('active_ids'))
        quotation = active_queue_ids.filtered(lambda x :x.queue_type == 'quotation')
        purchase_order = active_queue_ids.filtered(lambda x :x.queue_type == 'purchase_order')
        invoice = active_queue_ids.filtered(lambda x :x.queue_type == 'invoice')
        bills = active_queue_ids.filtered(lambda x :x.queue_type == 'bills')
        credit_notes = active_queue_ids.filtered(lambda x :x.queue_type == 'credit_note')
        debit_note = active_queue_ids.filtered(lambda x :x.queue_type == 'debit_note')
        journals = active_queue_ids.filtered(lambda x :x.queue_type == 'journal')
        if quotation:
            find_config._loop_through_quote_queue(quotation)
        if purchase_order:
            find_config.manually_from_queue_purchase(purchase_order)
        if invoice:
            find_config._import_invoices(invoice, 'out_invoice')
        if bills:
            find_config._import_invoices(bills, 'in_invoice')
        if credit_notes:
            find_config._import_refund(credit_notes, 'out_refund')
        if debit_note:
            find_config._import_refund(debit_note, 'in_refund')
        if journals:
            find_config._import_journals_from_queue(journals)
