# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class InvoiceXeros(models.Model):
    _inherit = 'account.move.line'

    sh_xero_invoice_line_id = fields.Char('Xero Invoice Line', copy=False)


class InvoiceXero(models.Model):
    _inherit = 'account.move'

    xero_invoice_number = fields.Char("Xero Invoice Number", copy=False)
    sh_xero_config = fields.Many2one('sh.xero.configuration', string="Xero Config", copy=False)
    sh_xero_invoice_id = fields.Char('Xero Invoice Id', copy=False)
    sh_xero_credit_note_id = fields.Char("Xero Credit Note", copy=False)
    xero_credit_note_number = fields.Char("Xero Credit Note Number", copy=False)
    sh_xero_manual_journal_id = fields.Char("Xero Journal ID", copy=False)
    failure_reason = fields.Char("Failed Reason", copy=False)

    def export_xero_invoice(self):
        invoice_active_ids = self.env['account.move'].browse(self.env.context.get('active_ids'))

        if not invoice_active_ids:
            return
        get_config = self.env['sh.xero.configuration'].search([('company_id', '=', self.env.user.company_id.id)])
        if not get_config:
            return get_config._popup('Export', 'Please generate the credentials first !')

        message = ''
        invoice = invoice_active_ids.filtered(lambda l: l.move_type == 'out_invoice')
        if invoice:
            message += get_config.final_invoice_export(invoice, 'invoice')

        credit_note = invoice_active_ids.filtered(lambda l: l.move_type == 'out_refund')
        if credit_note:
            message += get_config.final_credit_note_export(credit_note, 'credit_note')

        bills = invoice_active_ids.filtered(lambda l: l.move_type == 'in_invoice')
        if bills:
            message += get_config.final_invoice_export(bills, 'bills')

        refunds = invoice_active_ids.filtered(lambda l: l.move_type == 'in_refund')
        if refunds:
            message += get_config.final_credit_note_export(refunds, 'refund')

        # journal = invoice_active_ids.filtered(lambda l: l.journal_id.type == 'general')
        journal = invoice_active_ids.filtered(lambda l: l.move_type == 'entry')
        if journal:
            message += get_config.final_journal_export(journal)
            # return res

        if not message:
            message = 'Exported successfully'
        return get_config._popup('Export', message)
