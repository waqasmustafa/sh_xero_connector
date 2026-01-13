# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import api, models


class XeroReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    @api.model_create_multi
    def create(self, vals_ist):
        rest = super(XeroReconcile, self).create(vals_ist)
        for res in rest:
            if 'import_data' in self.env.context:
                continue
            invoice = []
            for data in res.credit_move_id.payment_id.reconciled_invoice_ids:
                for value in data.line_ids:
                    if value.id == res.debit_move_id.id:
                        invoice.append(data)
                        break
            if not invoice:
                for data in res.debit_move_id.payment_id.reconciled_invoice_ids:
                    for value in data.line_ids:
                        if value.id == res.credit_move_id.id:
                            invoice.append(data)
                            break
            payment = res.credit_move_id.payment_id
            if not payment:
                payment = res.debit_move_id.payment_id
            if invoice:
                domain = [('company_id', '=', self.env.company.id)]
                find_config = self.env['sh.xero.configuration'].search(
                    domain)
                invoice = invoice[0]
                if invoice.sh_xero_invoice_id:
                    xero_invoice = invoice.sh_xero_invoice_id
                else:
                    find_config.final_invoice_export(invoice, 'invoice')
                    xero_invoice = invoice.sh_xero_invoice_id
                if payment.sh_xero_prepayment_id or payment.sh_xero_overpayment_id:
                    valss = {
                        'Amount': res.amount,
                        'Invoice': {
                            'InvoiceID': xero_invoice
                        }
                    }
                    if payment.sh_xero_prepayment_id:
                        self.put_req('prepayments_by_id', data=valss, xero_id=payment.sh_xero_prepayment_id)
                    if payment.sh_xero_overpayment_id:
                        self.put_req('overpayments_by_id', data=valss, xero_id=payment.sh_xero_overpayment_id)
        return rest
