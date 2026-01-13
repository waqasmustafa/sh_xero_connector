# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import datetime
from odoo import fields, models


class XeroCredtNote(models.Model):
    _inherit = 'sh.xero.configuration'

    import_credit_note = fields.Boolean("Import Credit Note")
    export_credit_note = fields.Boolean("Export credit Note")
    auto_import_credit_note = fields.Boolean("Auto Import Credit Note")
    auto_export_credit_note = fields.Boolean("Auto Export Credit Note")
    last_sync_credit_note = fields.Datetime("LS Credit Note")
    last_sync_import_credit_note = fields.Date("LS Import Credit Note")

    def submit_credit_note(self):
        if self.import_credit_note:
            try:
                self.credit_note_import()
            except Exception as e:
                self._log(e, type_='credit_note')
        if self.export_credit_note:
            self.credit_note_export()

    # ------------------------------------------------
    #  Import Credit Notes From Xero
    # ------------------------------------------------

    def credit_note_import(self):
        credit_note_type = 'Type=="ACCRECCREDIT"'
        params = {
            'page': 1,
            'where': credit_note_type
        }
        if self.last_sync_import_credit_note:
            date = datetime.strptime(str(self.last_sync_import_credit_note), '%Y-%m-%d').date()
            params['where'] = f'{credit_note_type} AND Date>=DateTime({date.year}, {date.month}, {date.day})'
        import_count = 0
        while True:
            success,response_json = self.get_req('CreditNotes', params=params)
            if not success:
                break
            if not response_json.get('CreditNotes'):
                break
            for data in response_json['CreditNotes']:
                if data['Status'] != 'DELETED':
                    import_count += 1
                    name = data['CreditNoteNumber'] if 'CreditNoteNumber' in data else "Credit Note"
                    self._queue('credit_note', data['CreditNoteID'], name)
            params['page'] += 1
        if import_count:
            self._log(f"{import_count} Credit Note added to the queue", type_='credit_note', state='success')
            self.last_sync_import_credit_note = datetime.today().strftime('%Y-%m-%d')
        else:
            self._log("Not get any data to import", type_='credit_note', state='success')

    def import_records_from_queue_credit_note(self):
        domain = [('sh_current_state','=','draft'),('queue_type', '=', 'credit_note')]
        get_queue = self.env['sh.xero.queue'].search(domain,limit=40)
        if not get_queue:
            domain = [('sh_current_state','=','error'),('queue_type', '=', 'credit_note')]
            get_queue = self.env['sh.xero.queue'].search(domain,limit=5)
            if not get_queue:
                return
        self._import_refund(get_queue, 'out_refund')

    def _import_refund_status(self, queue, move_type):
        success,reason = queue.sh_current_config.final_credit_note_import(queue, move_type)
        if success:
            return success,reason
        if 'incompatible with your fiscal country' in reason:
            return self._import_refund_status(queue, move_type)
        elif 'is not balanced' in reason:
            return self._import_refund_status(queue, move_type)
        return success,reason

    def _import_refund(self,records, move_type):
        log_type = False
        if move_type == 'out_refund':
            log_type = 'credit_note'
        elif move_type == 'in_refund':
            log_type = 'refund'
        if not records:
            self._log("Not have any queue to import.", type_=log_type, state='success')
            return
        imported = failed = 0
        for queue in records:
            if queue.sh_id:
                success,reason = self._import_refund_status(queue, move_type)
                if success:
                    queue._done()
                    imported += 1
                else:
                    queue._error(reason)
                    failed += 1
            else:
                queue._error('Not have the Xero ID !')
                failed += 1
        if failed:
            self._log(f"{failed} {log_type.replace('_', ' ')}(s) failed to import from queue", type_=log_type)
        if imported:
            self._log(f"{imported} {log_type.replace('_', ' ')}(s) imported from queue", type_=log_type, state='success')

    def _prepare_credit_note_vals(self, data, move_type):
        vals = {
            'move_type': move_type,
            'sh_xero_credit_note_id': data['CreditNoteID'],
            'sh_xero_config': self.id,
            'xero_credit_note_number': data['CreditNoteNumber']
        }
        find_contact = self.env['res.partner'].search([('sh_xero_contact_id', '=', data['Contact']['ContactID'])], limit=1)
        if find_contact:
            vals['partner_id'] = find_contact.id
        else:
            self.create_emergency_contact(data['Contact']['ContactID'])
            find_contact = self.env['res.partner'].search([('sh_xero_contact_id', '=', data['Contact']['ContactID'])], limit=1)
            if find_contact:
                vals['partner_id'] = find_contact.id
        if 'DateString' in data:
            start_date_last_sync = data['DateString'].split('T')[0]
            final_last_sync = datetime.strptime(start_date_last_sync, '%Y-%m-%d')
            vals['invoice_date'] = final_last_sync
        if 'DueDateString' in data:
            start_date_last_syncs = data['DueDateString'].split('T')[0]
            final_last_syncs = datetime.strptime(start_date_last_syncs, '%Y-%m-%d')
            vals['invoice_date_due'] = final_last_syncs
        if 'CurrencyCode' in data:
            find_currency = self.env['res.currency'].search([('name', '=', data['CurrencyCode'])])
            if find_currency:
                vals['currency_id'] = find_currency.id
        if 'LineItems' in data:
            list_of_order_lines = []
            for value in data['LineItems']:
                line_vals = {
                    'quantity': value['Quantity'],
                    'price_unit': value['UnitAmount'],
                }
                if 'Description' in value and value['Description']:
                    line_vals['name'] = value['Description']
                if 'TaxType' in value and value['TaxType']:
                    domain = [('xero_tax_type', '=', value['TaxType'])]
                    if move_type == 'out_refund':
                        domain.append(('type_tax_use', '=', 'sale'))
                    elif move_type == 'in_refund':
                        domain.append(('type_tax_use', '=', 'purchase'))
                    find_tax = self.env['account.tax'].search(domain, limit=1)
                    if find_tax:
                        line_vals['tax_ids'] = find_tax.ids
                if 'AccountCode' in value and value['AccountCode']:
                    find_account = self.env['account.account'].search([('code', '=', value['AccountCode'])], limit=1)
                    if find_account:
                        line_vals['account_id'] = find_account.id
                if 'ItemCode' in value:
                    find_pro = self.env['product.product'].search([('default_code', '=', value['ItemCode'])])
                    if find_pro:
                        line_vals['product_id'] = find_pro.id
                list_of_order_lines.append((0, 0, line_vals))
            if list_of_order_lines:
                vals['invoice_line_ids'] = list_of_order_lines
        return vals

    def final_credit_note_import(self, credit_queue, move_type):
        try:
            success,response_json = self.get_req('credit_note_by_id', xero_id=credit_queue.sh_id)
            if not success:
                return False, response_json
            if not response_json.get('CreditNotes'):
                return False, "Don't get the data !"
            if len(response_json['CreditNotes']) > 1:
                return False, 'Multiple records found with same ID !'
            data = response_json['CreditNotes'][0]
            find_credits = self.env['account.move'].search([('sh_xero_credit_note_id', '=', data['CreditNoteID'])])
            if find_credits:
                # if 'Payments' in data and data['Payments']:
                if data.get('FullyPaidOnDate') and not data.get('RemainingCredit'):
                    if find_credits.invoice_line_ids and find_credits.state == 'draft':
                        find_credits.action_post()
            else:
                vals = self._prepare_credit_note_vals(data, move_type)
                create_credit = self.env['account.move'].create(vals)
                # if data.get('Payments'):
                if data.get('FullyPaidOnDate') and not data.get('RemainingCredit'):
                    if create_credit.invoice_line_ids and create_credit.state == 'draft':
                        create_credit.action_post()
            if self.manage_payments:
                self.import_payments()
            return True, ''
        except Exception as e:
            return False, str(e)

    def credit_note_export(self, cron=''):
        domain = [('sh_xero_config', '=', self.id),
                  ('move_type', '=', 'out_refund')]
        if self.last_sync_credit_note:
            domain.append(('write_date', '>', self.last_sync_credit_note))
        find_credit = self.env['account.move'].search(domain)
        mee = 'credit_note'
        if find_credit:
            self.final_credit_note_export(find_credit, mee)
        elif not cron:
            self._log("No New Credit Note To Export", type_='credit_note', state='success')

    def final_credit_note_export(self, find_credit, move_type):
        try:
            message = ''
            export_count = 0
            id_list = []
            all_payments = self.env['account.payment'].search([])
            for data in find_credit:
                # vals = self.generate_vals(data)
                success,vals = self.generate_vals(data)
                if not success:
                    data.write({'failure_reason': vals})
                    id_list.append(str(data.id))
                    message += f"\n{data.name}\nError: {vals}\n"
                    continue
                if data.sh_xero_credit_note_id:
                    vals['CreditNoteID'] = data.sh_xero_credit_note_id
                request_body = {"CreditNotes": [vals]}
                success,response_json = self.post_req('CreditNotes', data=request_body, log=False)
                if not success:
                    data.write({'failure_reason': response_json})
                    failed_reason = f"'{data.name}'\nError: {response_json}"
                    # self._log(failed_reason, type_=move_type)
                    message += f"\n{failed_reason}\n"
                    id_list.append(str(data.id))
                    continue
                for vva in response_json['CreditNotes']:
                    export_count += 1
                    data.write({
                        'sh_xero_credit_note_id': vva['CreditNoteID'],
                        'xero_credit_note_number': vva['CreditNoteNumber'],
                        'sh_xero_config': self.id,
                        'failure_reason': ''
                    })
                # Manage payments
                if self.manage_payments:
                    if move_type == 'credit_note':
                        inv_payments = all_payments.filtered(lambda payment: data.id in payment.reconciled_invoice_ids.ids)
                        self._manage_payment(inv_payments)
                    elif  move_type == 'refund':
                        bill_payments = all_payments.filtered(lambda payment: data.id in payment.reconciled_bill_ids.ids)
                        self._manage_payment(bill_payments)
            if id_list:
                self._log(f'{len(id_list)} record(s) failed to export !', type_=move_type, failed=id_list)

            if export_count:
                log_msg = f'{export_count} {move_type} exported'
                self._log(log_msg, type_=move_type, state='success')
                message = f'\n{log_msg}\n{message}'
            if move_type == 'credit_note':
                self.last_sync_credit_note = datetime.now()
            elif  move_type == 'refund':
                self.last_sync_refund = datetime.now()
            return message
        except Exception as e:
            self._log(e, type_='credit_note')
            return f'\nExport {move_type} error:\n{e}\n'

    def _xero_credit_note_cron(self):
        get_objects = self.env['sh.xero.configuration'].search([])
        if not get_objects:
            return
        for record in get_objects:
            if record.auto_import_credit_note:
                record.credit_note_import()
            if record.auto_export_credit_note:
                record.credit_note_export('Cron: ')
