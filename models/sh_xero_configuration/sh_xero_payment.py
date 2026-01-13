# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import fields, models

XERO_PAYMENT_TYPE = {
    'ACCRECPAYMENT': ('customer', 'inbound'),
    'ACCPAYPAYMENT': ('supplier', 'outbound'),
    'APCREDITPAYMENT': ('supplier', 'inbound'),
    'ARCREDITPAYMENT': ('customer', 'outbound'),
    'ARPREPAYMENTPAYMENT': ('customer', 'inbound'),
    'APPREPAYMENTPAYMENT': ('supplier', 'outbound'),
    'AROVERPAYMENTPAYMENT': ('customer', 'inbound'),
    'APOVERPAYMENTPAYMENT': ('supplier', 'outbound'),
}


class XeroPayment(models.Model):
    _inherit = 'sh.xero.configuration'

    sh_journal = fields.Many2one('account.journal', domain=[('type', 'in', ('bank', 'cash'))], string="Default Journal")
    default_overpayment = fields.Many2one('account.journal', string="Default OverPayment Journal")
    default_prepayment = fields.Many2one('account.journal', string="Default PrePayment Journal")
    manage_payments = fields.Boolean("Manage Payments")
    manage_overpayment = fields.Boolean("Manage OverPayments")
    manage_prepayment = fields.Boolean("Manage PrePayments")
    last_sync_payments = fields.Datetime("LS Payments")

    def compute_date(self, datestring):
        time = datestring.split('(')[1].split(')')[0]
        milliseconds = int(time[:-5])
        hours = int(time[-5:]) / 100
        times = milliseconds / 1000
        dt = datetime.utcfromtimestamp(times + hours * 3600)
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + '%02d:00' % hours

    def import_xero_payments(self):
        if not (self.manage_payments or self.manage_overpayment or self.manage_prepayment):
            return
        msg_list = []
        failed_list = []
        if self.manage_payments:
            success, msg = self.import_payments()
            if success:
                if msg:
                    msg_list.append(msg)
            else:
                failed_list.append(msg)
        if self.manage_overpayment:
            success, msg = self.import_overpayment()
            if success:
                if msg:
                    msg_list.append(msg)
            else:
                failed_list.append(msg)
        if self.manage_prepayment:
            success, msg = self.import_prepayment()
            if success:
                if msg:
                    msg_list.append(msg)
            else:
                failed_list.append(msg)

        if msg_list:
            self._log(', '.join(msg_list), type_='payment', state='success')
        if failed_list:
            self._log(', '.join(failed_list), type_='payment')

        if not (msg_list or failed_list):
            self._log('Imported successfully', type_='payment', state='success')

    # --------------------------------------------
    #  Prepare Payment Vals
    # --------------------------------------------

    def _prepare_payment_vals(self, data, final_date):
        vals = {
            'amount': data['Amount'],
            'sh_xero_config': self.id,
            'sh_xero_payment_id': data['PaymentID'],
            'date': final_date
        }
        if 'Reference' in data and data['Reference']:
            vals['ref'] = data['Reference']
        if 'CurrencyCode' in data['Invoice']:
            domain = [
                ('name', '=', data['Invoice']['CurrencyCode'])]
            find_currency = self.env['res.currency'].search(domain)
            if find_currency:
                vals['currency_id'] = find_currency.id
        find_journal = self.env['res.partner.bank'].search([
            ('sh_xero_account_id', '=', data['Account']['AccountID'])])
        if find_journal:
            vals['journal_id'] = find_journal.journal_id.id
            vals['partner_bank_id'] = find_journal.id
        else:
            get_journal = self.env['account.journal'].search([
                ('name', '=', self.sh_journal.name)])
            if get_journal:
                vals['journal_id'] = get_journal.id
        find_contact = self.env['res.partner'].search([('sh_xero_contact_id', '=', data['Invoice']['Contact']['ContactID'])])
        if find_contact:
            vals['partner_id'] = find_contact.id

        if data.get('PaymentType'):
            if XERO_PAYMENT_TYPE.get(data['PaymentType']):
                vals['partner_type'] = XERO_PAYMENT_TYPE[data['PaymentType']][0]
                vals['payment_type'] = XERO_PAYMENT_TYPE[data['PaymentType']][1]
                if vals['payment_type'] == 'inbound':
                    vals['payment_method_id'] = self.env.ref('account.account_payment_method_manual_in').id
                else:
                    vals['payment_method_id'] = self.env.ref('account.account_payment_method_manual_out').id
        return vals

    def _get_final_date(self, xero_date):
        pay_date = self.compute_date(xero_date)
        pay_dates = pay_date.split('T')
        return datetime.strptime(pay_dates[0], '%Y-%m-%d')

    # --------------------------------------------
    #  Import Payments
    # --------------------------------------------

    def import_payments(self):
        if not self.sh_journal:
            return False, "Please Select Default Journal for Non-Journal Accounts"
        success,response_json = self.get_req('Payments')
        if not success:
            return False, response_json
        if not response_json.get('Payments'):
            return True, ''
        current_date = datetime.now() + relativedelta(years=100)
        import_count = 0
        for data in response_json['Payments']:
            find_payment = self.env['account.payment'].search([('sh_xero_payment_id', '=', data['PaymentID'])])
            if find_payment:
                continue
            final_date = self._get_final_date(data['Date'])
            if final_date > current_date:
                continue
            # if final_date < current_date:
            find_invoice = self.env['account.move'].search([
                '|',
                ('sh_xero_invoice_id', '=', data['Invoice']['InvoiceID']),
                ('sh_xero_credit_note_id', '=', data['Invoice']['InvoiceID'])
            ])
            if find_invoice.state != 'posted':
                continue
            # if find_invoice.state == 'posted':
            vals = self._prepare_payment_vals(data, final_date)
            register_pay = self.env['account.payment'].create(vals)
            import_count += 1
            register_pay.action_post()
            # reconcile
            payment_lines = register_pay.move_id.mapped('line_ids')
            invoice_lines = find_invoice.mapped('line_ids')
            lines = invoice_lines.filtered(lambda line: line.account_id.reconcile and line.account_id.account_type in ('liability_payable', 'asset_receivable') and not line.reconciled)
            lines += payment_lines.filtered(lambda line: line.account_id.reconcile and line.account_id.account_type in ('liability_payable', 'asset_receivable') and not line.reconciled)
            lines.reconcile()
        # self.last_sync_import_payment = datetime.today().strftime('%Y-%m-%d')
        if import_count:
            return True, f'{import_count} payment(s) imported'
        return True, ''

    # --------------------------------------------
    #  Import Prepayments
    # --------------------------------------------

    def import_prepayment(self):
        if not self.default_prepayment:
            return False, "Please Select Default Prepayment Journal"
        success,response_json = self.get_req('Prepayments')
        if not success:
            return False, response_json
        if not response_json.get('Prepayments'):
            return True, ''
        current_date = datetime.now() + relativedelta(years=100)
        import_count = 0
        for data in response_json['Prepayments']:
            final_date = self._get_final_date(data['Date'])
            if final_date > current_date:
                continue
            vals = {
                'amount': data['SubTotal'],
                'sh_xero_config': self.id,
                'journal_id': self.default_prepayment.id
            }
            if 'Reference' in data and data['Reference']:
                vals['ref'] = data['Reference']
            if 'CurrencyCode' in data:
                domain = [('name', '=', data['CurrencyCode'])]
                find_currency = self.env['res.currency'].search(domain)
                if find_currency:
                    vals['currency_id'] = find_currency.id
            # if final_date < current_date:
            vals['date'] = final_date
            find_contact = False
            domain = [('sh_xero_contact_id', '=', data['Contact']['ContactID'])]
            find_contact = self.env['res.partner'].search(domain)
            if find_contact.company_type == 'company':
                vals['partner_id'] = find_contact.id
            else:
                vals['partner_id'] = find_contact.parent_id.id
            if data['Type'] == 'RECEIVE-PREPAYMENT':
                vals['payment_type'] = 'inbound'
                vals['partner_type'] = 'customer'
            elif data['Type'] == 'SPEND-PREPAYMENT':
                vals['payment_type'] = 'outbound'
                vals['partner_type'] = 'supplier'
            if vals['payment_type'] == 'inbound':
                payment_method = self.env.ref('account.account_payment_method_manual_in')
            else:
                payment_method = self.env.ref('account.account_payment_method_manual_out')
            vals['payment_method_id'] = payment_method.id
            domain = [('sh_xero_prepayment_id', '=', data['PrepaymentID'])]
            find_prepayment = self.env['account.payment'].search(domain)
            if find_prepayment:
                self.check_reconsile(data, find_contact, find_prepayment)
            else:
                vals['sh_xero_prepayment_id'] = data['PrepaymentID']
                register_prepay = self.env['account.payment'].create(vals)
                import_count += 1
                register_prepay.action_post()
                self.check_reconsile(data, find_contact, register_prepay)
        # self.last_sync_import_prepayment = datetime.today().strftime('%Y-%m-%d')
        if import_count:
            return True, f'{import_count} prepayment(s) imported'
        return True, ''

    # --------------------------------------------
    #  Import Overpayments
    # --------------------------------------------

    def import_overpayment(self):
        if not self.default_overpayment:
            return False, "Please Select Default Overpayment Journal"
        success,response_json = self.get_req('Overpayments')
        if not success:
            return False, response_json
        if not response_json.get('Overpayments'):
            return True, ''
        current_date = datetime.now() + relativedelta(years=100)
        import_count = 0
        for data in response_json['Overpayments']:
            final_date = self._get_final_date(data['Date'])
            if final_date > current_date:
                continue
            vals = {
                'amount': data['SubTotal'],
                'sh_xero_config': self.id,
                'journal_id': self.default_overpayment.id
            }
            if 'Reference' in data and data['Reference']:
                vals['ref'] = data['Reference']
            if 'CurrencyCode' in data:
                domain = [('name', '=', data['CurrencyCode'])]
                find_currency = self.env['res.currency'].search(domain)
                if find_currency:
                    vals['currency_id'] = find_currency.id
            # if final_date < current_date:
            vals['date'] = final_date
            find_contact = False
            domain = [('sh_xero_contact_id', '=', data['Contact']['ContactID'])]
            find_contact = self.env['res.partner'].search(domain)
            if find_contact.company_type == 'company':
                vals['partner_id'] = find_contact.id
            else:
                vals['partner_id'] = find_contact.parent_id.id
            if data['Type'] == 'RECEIVE-OVERPAYMENT':
                vals['payment_type'] = 'inbound'
                vals['partner_type'] = 'customer'
            elif data['Type'] == 'SPEND-OVERPAYMENT':
                vals['payment_type'] = 'outbound'
                vals['partner_type'] = 'supplier'
            if vals['payment_type'] == 'inbound':
                payment_method = self.env.ref('account.account_payment_method_manual_in')
            else:
                payment_method = self.env.ref('account.account_payment_method_manual_out')
            vals['payment_method_id'] = payment_method.id
            domain = [('sh_xero_overpayment_id',
                        '=', data['OverpaymentID'])]
            find_overpayment = self.env['account.payment'].search(domain)
            if find_overpayment:
                self.check_reconsile(data, find_contact, find_overpayment)
            else:
                vals['sh_xero_overpayment_id'] = data['OverpaymentID']
                register_overpay = self.env['account.payment'].create(vals)
                import_count += 1
                register_overpay.action_post()
                self.check_reconsile(data, find_contact, register_overpay)
        # self.last_sync_import_overpayment = datetime.today().strftime('%Y-%m-%d')
        if import_count:
            return True, f'{import_count} overpayment(s) imported'
        return True, ''

    def check_reconsile(self, data, find_contact, find_overpayment):
        if data['Type'] == 'RECEIVE-OVERPAYMENT' or data['Type'] == 'RECEIVE-PREPAYMENT':
            if abs(find_contact.credit) != data['RemainingCredit']:
                if data['Allocations']:
                    amount_list = []
                    for value in data['Allocations']:
                        amount = value['Amount']
                        amount_list.append(amount)
                        domain = [('sh_xero_invoice_id', '=', value['Invoice']['InvoiceID'])]
                        find_invoices = self.env['account.move'].search(domain)
                        if find_invoices.state == 'draft':
                            find_invoices.action_post()
                        some = 'check'
                        already_created = self.sh_reconsile(
                            find_overpayment, find_invoices, amount, some)
                        if not already_created:
                            some = 'create'
                            self.sh_reconsile(find_overpayment, find_invoices, amount, some)
                    self.sh_delete_reconsile(find_overpayment, amount_list)
        if data['Type'] == 'SPEND-OVERPAYMENT' or data['Type'] == 'SPEND-PREPAYMENT':
            if abs(find_contact.debit) != data['RemainingCredit']:
                if data['Allocations']:
                    amount_list = []
                    for value in data['Allocations']:
                        amount = value['Amount']
                        amount_list.append(amount)
                        domain = [('sh_xero_invoice_id', '=',
                                   value['Invoice']['InvoiceID'])]
                        find_invoices = self.env['account.move'].search(domain)
                        if find_invoices.state == 'draft':
                            find_invoices.action_post()
                        some = 'check'
                        already_created = self.sh_reconsile(
                            find_overpayment, find_invoices, amount, some)
                        if not already_created:
                            some = 'create'
                            self.sh_reconsile(
                                find_overpayment, find_invoices, amount, some)
                    self.sh_delete_reconsile(find_overpayment, amount_list)

    def sh_delete_reconsile(self, register_pay, amount):
        payment_lines = register_pay.move_id.mapped('line_ids')
        c_lines = payment_lines.filtered(
            lambda line: line.account_id.reconcile and line.account_id.account_type in ('liability_payable', 'asset_receivable') and not line.reconciled)
        domain = [('credit_move_id', '=', c_lines.id)]
        get_som = self.env['account.partial.reconcile'].search(domain)
        if get_som:
            for value in get_som:
                if value.amount not in amount:
                    value.unlink()

    def sh_reconsile(self, register_pay, find_invoice, amount, some):
        payment_lines = register_pay.move_id.mapped('line_ids')
        invoice_lines = find_invoice.mapped('line_ids')
        d_lines = invoice_lines.filtered(
            lambda line: line.account_id.reconcile and line.account_id.account_type in ('liability_payable', 'asset_receivable') and not line.reconciled)
        c_lines = payment_lines.filtered(
            lambda line: line.account_id.reconcile and line.account_id.account_type in ('liability_payable', 'asset_receivable') and not line.reconciled)
        if d_lines and c_lines:
            if some == 'create':
                vals = {
                    'debit_move_id': d_lines.id,
                    'credit_move_id': c_lines.id,
                    'amount': amount,
                    'debit_amount_currency': amount,
                    'credit_amount_currency': amount,
                }
                self.env['account.partial.reconcile'].with_context(
                    import_data=True).create(vals)
            if some == 'check':
                domain = [('debit_move_id', '=', d_lines.id),
                          ('credit_move_id', '=', c_lines.id)]
                get_som = self.env['account.partial.reconcile'].search(domain)
                if get_som:
                    for value in get_som:
                        if value.amount == amount:
                            return True
                        return False
                else:
                    return False

    def _manage_payment(self, get_all_payments):
        already_in_xero = failed = exported = 0
        for data in get_all_payments:
            if data.sh_xero_payment_id and data.sh_xero_config:
                already_in_xero += 1
                continue
            invoice = data.reconciled_invoice_ids or data.reconciled_bill_ids
            if not invoice:
                exported += 1
                continue
            for inv in invoice:
                xero_account_id = self._get_xero_bank_acc_id(data)

                if not xero_account_id:
                    failed += 1
                    self._log(f"'{data.name}' payment failed to export !", type_='payment')
                    continue

                if inv.amount_residual == 0.00:
                    final_invoice_amount = inv.amount_total
                else:
                    final_invoice_amount = inv.amount_total - inv.amount_residual
                vals = {
                    'Date': inv.date,
                    'Amount': final_invoice_amount,
                    'Reference': data.ref if data.ref else '',
                    'Account': {'AccountID': xero_account_id},
                    'CurrencyRate': data.currency_id.rate
                }
                if not (inv.sh_xero_invoice_id or inv.sh_xero_credit_note_id):
                    continue
                if inv.move_type in ('out_invoice', 'in_invoice'):
                    vals['Invoice'] = {'InvoiceID': inv.sh_xero_invoice_id}
                if inv.move_type in ('out_refund', 'in_refund'):
                    vals['CreditNote'] = {'CreditNoteID': inv.sh_xero_credit_note_id}
                request_body = {"Payments": [vals]}
                success,response_json = self.put_req('Payments', data=request_body)
                if not success:
                    failed += 1
                    continue
                exported += 1
                for daa in response_json['Payments']:
                    data.write({
                        'sh_xero_payment_id': daa['PaymentID'],
                        'sh_xero_config': self.id
                    })
        msg_list = []
        if exported:
            msg_list.append(f'{exported} payment(s) are exported')
            self.last_sync_payments = datetime.now()
        if already_in_xero:
            msg_list.append(f'{already_in_xero} payment(s) are already in Xero')
        if failed:
            msg_list.append(f'{failed} payment(s) are failed to export !')
            # self._log(f'{failed} payment(s) are failed to export !', type_='payment')
        if not msg_list:
            msg_list.append('Payments are up to date')
        return self._popup('Export Payment', '\n\n'.join(msg_list))

    def send_payments(self):
        domain = [('sh_xero_overpayment_id', '=', False), ('sh_xero_prepayment_id', '=', False)]
        if self.last_sync_payments:
            domain.append(('write_date', '>', self.last_sync_payments))
        get_all_payments = self.env['account.payment'].search(domain)
        if get_all_payments:
            self._manage_payment(get_all_payments)

    def _get_xero_bank_acc_id(self, data):
        bank_acc = False
        if self.sh_journal:
            if self.sh_journal.bank_account_id:
                bank_acc = self.sh_journal.bank_account_id
                if bank_acc.sh_xero_account_id:
                    return bank_acc.sh_xero_account_id
        if data.journal_id:
            if data.journal_id.bank_account_id:
                bank_acc = data.journal_id.bank_account_id
                if bank_acc.sh_xero_account_id:
                    return bank_acc.sh_xero_account_id
        if bank_acc:
            self._export_bank(self, bank_acc)
            if bank_acc.sh_xero_account_id:
                return bank_acc.sh_xero_account_id
        return False

    def _xero_payments_cron(self):
        get_objects = self.env['sh.xero.configuration'].search([])
        for record in get_objects:
            if record.manage_payments:
                record.import_xero_payments()
