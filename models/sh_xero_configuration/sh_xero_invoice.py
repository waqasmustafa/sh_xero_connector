# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import datetime
from odoo import fields, models

MOVE_TYPE = {
    'in_invoice': 'ACCPAY',
    'out_invoice': 'ACCREC',
    'in_refund': 'ACCPAYCREDIT',
    'out_refund': 'ACCRECCREDIT'
}


class XeroInvoice(models.Model):
    _inherit = 'sh.xero.configuration'

    import_invoice = fields.Boolean("Import Invoices")
    export_invoice = fields.Boolean("Export Invoices")
    auto_import_invoice = fields.Boolean("Auto Import Invoices")
    auto_export_invoice = fields.Boolean("Auto Export Invoices")
    last_sync_invoice = fields.Datetime("LS Invoices")
    last_sync_import_invoice = fields.Date("Ls Import Invoice")

    def submit_invoice(self):
        if self.import_invoice:
            self.invoice_import()
        if self.export_invoice:
            self.invoice_export()

    def invoice_import(self):
        try:
            invoice_type = 'Type=="ACCREC"'
            params = {
                'page': 1,
                'where': invoice_type
            }
            if self.last_sync_import_invoice:
                date = datetime.strptime(str(self.last_sync_import_invoice), '%Y-%m-%d').date()
                params['where'] = f'{invoice_type} AND Date>=DateTime({date.year}, {date.month}, {date.day})'
            import_count = 0
            while True:
                success,response_json = self.get_req('Invoices', params=params)
                if not success:
                    break
                if not response_json.get('Invoices'):
                    break
                for data in response_json['Invoices']:
                    if data['Status'] in ('VOIDED', 'DELETED'):
                        continue
                    import_count += 1
                    name = data.get('InvoiceNumber') if data.get('InvoiceNumber') else "Invoice"
                    self._queue('invoice', data['InvoiceID'], name)
                params['page'] += 1
            if import_count:
                self._log(f"{import_count} Invoice added to the queue", type_='invoice', state='success')
                self.last_sync_import_invoice = datetime.today().strftime('%Y-%m-%d')
            else:
                self._log("Not find any new invoice to import", type_='invoice', state='success')
        except Exception as e:
            self._log(e, type_='invoice', state='error')

    # --------------------------------------------
    #  Cron: Import Invoices
    # --------------------------------------------

    def import_records_from_queue_invoice(self):
        domain = [('sh_current_state','=','draft'),('queue_type', '=', 'invoice')]
        get_queue = self.env['sh.xero.queue'].search(domain,limit=40)
        if not get_queue:
            domain = [('sh_current_state','=','error'),('queue_type', '=', 'invoice')]
            get_queue = self.env['sh.xero.queue'].search(domain,limit=5)
            if not get_queue:
                return
        self._import_invoices(get_queue, 'out_invoice')

    # --------------------------------------------
    #  Import Invoices
    # --------------------------------------------

    def _import_invoices(self, records, move_type):
        log_type = False
        if move_type == 'out_invoice':
            log_type = 'invoice'
        elif move_type == 'in_invoice':
            log_type = 'bill'
        if not records:
            self._log("Don't get any queue to import !", type_=log_type, state='success')
            return
        failed = imported = 0
        for queue in records:
            if not queue.sh_id:
                queue._error('Not has Xero ID !')
                failed += 1
                continue
            success,reason = queue.sh_current_config.final_import_invoice(queue, move_type)
            if success:
                queue._done()
                imported += 1
            else:
                queue._error(reason)
                failed += 1
        if failed:
            self._log(f"{failed} {log_type}(s) Failed to Imported From Queue", type_=log_type)
        if imported:
            self._log(f"{imported} {log_type}(s) Imported Successfully From Queue", type_=log_type, state='success')

    # --------------------------------------------
    #  Prepare Invoices Vals
    # --------------------------------------------

    def _prepare_invoice_vals(self, data, move_type):
        vals = {
            'move_type': move_type,
            'sh_xero_config': self.id,
            'xero_invoice_number': data['InvoiceNumber'],
            'sh_xero_invoice_id': data['InvoiceID']
        }
        if 'Reference' in data and data['Reference']:
            vals['payment_reference'] = data['Reference']
        domain = [('sh_xero_contact_id', '=',
                    data['Contact']['ContactID'])]
        find_contact = self.env['res.partner'].search(
            domain, limit=1)
        if find_contact:
            vals['partner_id'] = find_contact.id
        else:
            self.create_emergency_contact(
                data['Contact']['ContactID'])
            domain = [('sh_xero_contact_id', '=',
                        data['Contact']['ContactID'])]
            find_contact = self.env['res.partner'].search(
                domain, limit=1)
            if find_contact:
                vals['partner_id'] = find_contact.id
        if 'DateString' in data:
            start_date_last_sync = data['DateString'].split('T')[
                0]
            final_last_sync = datetime.strptime(
                start_date_last_sync, '%Y-%m-%d')
            vals['invoice_date'] = final_last_sync
        if 'DueDateString' in data:
            start_date_last_syncs = data['DueDateString'].split('T')[
                0]
            final_last_syncs = datetime.strptime(
                start_date_last_syncs, '%Y-%m-%d')
            vals['invoice_date_due'] = final_last_syncs
        if 'CurrencyCode' in data:
            domain = [('name', '=', data['CurrencyCode'])]
            find_currency = self.env['res.currency'].search(
                domain)
            if find_currency:
                vals['currency_id'] = find_currency.id
        return vals

    # --------------------------------------------
    #  Prepare Invoices Line Vals
    # --------------------------------------------

    def _prepare_move_line_vals(self, data, value, final_quote):
        line_vals = {}
        if 'Quantity' in value:
            line_vals['quantity'] = value['Quantity']
        if 'LineAmountTypes' in data:
            if data['LineAmountTypes'] == 'Inclusive':
                if 'LineAmount' in value:
                    unit_price = (
                        value['LineAmount'] - value['TaxAmount']) / value['Quantity']
                    line_vals['price_unit'] = unit_price
            elif 'UnitAmount' in value:
                line_vals['price_unit'] = value['UnitAmount']
        elif 'UnitAmount' in value:
            line_vals['price_unit'] = value['UnitAmount']
        if 'Description' in value and value['Description']:
            line_vals['name'] = value['Description']
        if 'DiscountRate' in value:
            line_vals['discount'] = value['DiscountRate']
        if 'Item' in value:
            domain = [('sh_xero_product_id', '=', value['Item']['ItemID'])]
            find_pro = self.env['product.product'].search(
                domain)
            if find_pro:
                line_vals['product_id'] = find_pro.id
                accounts = find_pro.product_tmpl_id.get_product_accounts(
                    final_quote.fiscal_position_id)
                if accounts:
                    line_vals['account_id'] = accounts['expense'].id
        else:
            find_pro = self.env['product.product'].sudo().search(
                [], limit=1)
            if find_pro:
                accounts = find_pro.product_tmpl_id.get_product_accounts(
                    final_quote.fiscal_position_id)
                if accounts:
                    line_vals['account_id'] = accounts['expense'].id
        return line_vals

    # --------------------------------------------
    #  Import Invoices
    # --------------------------------------------

    def final_import_invoice(self, invoice_queue, move_type):
        try:
            success,response_json = self.get_req('invoice_by_id', xero_id=invoice_queue.sh_id)
            if not success:
                return False, response_json
            if not response_json.get('Invoices'):
                return False, "Don't get any data !"
            if len(response_json.get('Invoices')) > 1:
                return False, "Get multiple invoces for the same ID !"
            data = response_json['Invoices'][0]
            find_quotes = self.env['account.move'].search([('sh_xero_invoice_id', '=', data['InvoiceID'])])
            if find_quotes:
                return True, ''
            if data['Status'] == 'VOIDED':
                return False, 'A Voided Invoice !'
            vals = self._prepare_invoice_vals(data, move_type)
            final_quote = self.env['account.move'].create(vals)
            # if 'LineItems' in data:
            if not data.get('LineItems'):
                return True, ''
            for value in data['LineItems']:
                line_vals = self._prepare_move_line_vals(data, value, final_quote)
                find_line = self.env['account.move.line'].search([('sh_xero_invoice_line_id', '=', value['LineItemID'])])
                if find_line:
                    find_line.with_context(check_move_validity=False).write(line_vals)
                else:
                    line_vals['sh_xero_invoice_line_id'] = value['LineItemID']
                    line_vals['move_id'] = final_quote.id
                    if 'TaxType' in value and value['TaxType']:
                        domain = [('xero_tax_type', '=', value['TaxType'])]
                        if move_type == 'out_invoice':
                            domain.append(('type_tax_use', '=', 'sale'))
                        elif move_type == 'in_invoice':
                            domain.append(('type_tax_use', '=', 'purchase'))
                        find_tax = self.env['account.tax'].search(
                            domain, limit=1)
                        if find_tax:
                            line_vals['tax_ids'] = find_tax.ids
                    self.env['account.move.line'].with_context(check_move_validity=False).create(line_vals)
                    # invoice_line_id = self.env['account.move.line'].with_context(check_move_validity=False).create(line_vals)
                    # invoice_line_id._onchange_mark_recompute_taxes()
            final_quote.with_context(check_move_validity=False)._onchange_partner_id()
            # final_quote._recompute_tax_lines()
            if final_quote.amount_residual == 0.00 and data['Status'] == 'PAID' and final_quote.state == 'draft' and final_quote.invoice_line_ids and final_quote.partner_id:
                final_quote.action_post()
            payment_list = self.have_payment()
            if payment_list and data['InvoiceID'] in payment_list:
                if final_quote.invoice_line_ids and final_quote.state == 'draft' and final_quote.partner_id:
                    final_quote.action_post()
            return True, ''
        except Exception as e:
            return False, e

    def have_payment(self):
        success,response_json = self.get_req('Payments')
        if not success:
            return False
        if not response_json.get('Payments'):
            return False
        invoice_list = []
        for data in response_json['Payments']:
            invoice_list.append(data['Invoice']['InvoiceID'])
        if invoice_list:
            return invoice_list
        return False

    def invoice_export(self):
        domain = [('move_type', '=', 'out_invoice'), ('sh_xero_config', '=', self.id)]
        if self.last_sync_invoice:
            domain.append(('write_date', '>', self.last_sync_invoice))
        get_invoice = self.env['account.move'].search(domain)
        mee = 'invoice'
        if get_invoice:
            self.final_invoice_export(get_invoice, mee)
        else:
            self._log("No New Invoice To Export", type_='invoice', state='success')

    def generate_vals(self, data, check_product=False, product_reason=False):
        if not data.partner_id:
            return False, 'Please provide the customer/vendor !'
        if not data.invoice_line_ids:
            return False, 'Atleast one or more lines are required in xero to create the record on Xero !'
        vals = {
            'Type': MOVE_TYPE.get(data.move_type),
            'CurrencyCode': data.currency_id.name
            # 'CurrencyCode': 'AUD'
        }
        if not (data.partner_id.sh_xero_contact_id and data.partner_id.sh_xero_config):
            # self.final_contact_export(data.partner_id)
            self._quick_export_contact(data.partner_id)
        if data.partner_id.sh_xero_contact_id:
            vals['Contact'] = {
                'ContactID': data.partner_id.sh_xero_contact_id,
                # 'Name': data.partner_id.name,
            }
        else:
            return False, f"Export the '{data.partner_id.name}' Customer/Vendor first !"
        if data.payment_reference:
            vals['Reference'] = data.payment_reference
        if data.invoice_date:
            vals['DateString'] = datetime.strftime(data.invoice_date, "%Y-%m-%dT00:00:00Z")
        if data.invoice_date_due:
            vals['DueDateString'] = datetime.strftime(data.invoice_date_due, "%Y-%m-%dT00:00:00Z")
        if data.state == 'posted':
            vals['status'] = 'AUTHORISED'
        if data.sh_xero_invoice_id:
            vals['InvoiceID'] = data.sh_xero_invoice_id
        if not data.invoice_line_ids:
            return True, vals
        item_list = []
        failure_reason = False
        for line in data.invoice_line_ids:
            if line.display_type != 'product':
                continue
            # if not line.product_id:
            #     failure_reason = f"Please add a product in line to proceed !"
            #     break
            line_vals = {
                'Description': line.name,
                'Quantity': line.quantity,
                'UnitAmount': line.price_unit,
            }
            if line.account_id:
                success,account_code = self._get_acc_code(line.account_id)
                if not success:
                    failure_reason = f"{account_code} \nYou can map it with Xero account in 'Account Config'"
                    break
                line_vals['AccountCode'] = account_code
            if line.product_id:
                # Call from recursion
                item_code = line.product_id.default_code if line.product_id.default_code else line.product_id.name
                if check_product and item_code in product_reason:
                    success,failure_reason = self._search_product_in_xero(line.product_id)
                    if not success:
                        break
                # =============
                if not (line.product_id.sh_xero_product_id and line.product_id.sh_xero_config):
                    # need to export the line product first ...
                    success,failure_reason = self._search_product_in_xero(line.product_id)
                    if not success:
                        break
                line_vals['ItemCode'] = item_code
            if len(line.tax_ids) == 1:
                if line.tax_ids.xero_tax_type:
                    line_vals['TaxType'] = line.tax_ids.xero_tax_type
            if line.sh_xero_invoice_line_id:
                line_vals['LineItemID'] = line.sh_xero_invoice_line_id
            item_list.append(line_vals)
        if failure_reason:
            return False, failure_reason
        vals['LineItems'] = item_list
        return True, vals

    def _search_product_in_xero(self, product):
        # item_code = product.default_code if product.default_code else product.name
        # # Search Product
        # success,response_json = self.get_req('Items', params={'where': f'Code="{item_code}"'})
        # if success:
        #     if response_json.get('Items'):
        #         if len(response_json['Items']) == 1:
        #             product.write({
        #                 'sh_xero_product_id': response_json['Items'][0]['ItemID'],
        #             })
        #             return True, ''
        error = f"Failed to export the product '{product.name}' on Xero ! Please check that product variant's failure reason !"
        if self._export_product_variant(product, product.product_tmpl_id):
            return True, ''
        elif product.failure_reason:
            error = f"Error: {product.failure_reason}"
        return False, error

    def _export_inv(self, vals, invoice):
        request_body = {"Invoices": [vals]}
        success,response_json = self.post_req('Invoices', data=request_body, log=False)
        if success:
            return success,response_json
        # If there is a contact issue,
        # then try to find it using the name
        if 'The Contact Name already exists' in response_json:
            success,response_json = self.get_req('Contacts', params={'where': f'Name="{vals["Contact"]["Name"]}"'})
            if success:
                if response_json.get('Contacts'):
                    if len(response_json['Contacts']) == 1:
                        invoice.partner_id.write({
                            'sh_xero_contact_id': response_json['Contacts'][0]['ContactID'],
                        })
                        vals["Contact"]["ContactID"] = invoice.partner_id.sh_xero_contact_id
                        return self._export_inv(vals, invoice)
        if 'Item code ' in response_json:
            success,vals = self.generate_vals(invoice, check_product=True, product_reason=response_json)
            if success:
                return self._export_inv(vals, invoice)
            return success,vals
        return success,response_json

    def final_invoice_export(self, get_invoice, mee):
        if not get_invoice:
            return '\nPlease select the records to export !\n'
        message = ''
        move_type = False
        if mee == 'invoice':
            move_type = 'invoice'
            self.last_sync_invoice = datetime.now()
        elif  mee == 'bills':
            move_type = 'bill'
            self.last_sync_bill = datetime.now()
        try:
            export_count = 0
            id_list = []
            all_payments = self.env['account.payment'].search([])
            for data in get_invoice:
                success,vals = self.generate_vals(data)
                if not success:
                    data.write({'failure_reason': vals})
                    id_list.append(str(data.id))
                    message += f"\n{data.name}\nError: {vals}\n"
                    continue
                success,response_json = self._export_inv(vals, data)
                if not success:
                    data.write({'failure_reason': response_json})
                    id_list.append(str(data.id))
                    message += f"\n{data.name}\nError: {response_json}\n"
                    continue
                for vva in response_json['Invoices']:
                    export_count += 1
                    data.write({
                        'sh_xero_invoice_id': vva['InvoiceID'],
                        'xero_invoice_number': vva['InvoiceNumber'],
                        'sh_xero_config': self.id,
                        'failure_reason': ''
                    })
                    if len(data.invoice_line_ids) == 1:
                        for line in vva['LineItems']:
                            data.invoice_line_ids.write({
                                'sh_xero_invoice_line_id': line['LineItemID']
                            })
                    elif len(data.invoice_line_ids) >= 2:
                        for order_l in data.invoice_line_ids:
                            for line in vva['LineItems']:
                                if line['UnitAmount'] == order_l.price_unit and line['ItemCode'] == order_l.product_id.default_code:
                                    order_l.write({
                                        'sh_xero_invoice_line_id': line['LineItemID']
                                    })
                # Manage payments
                if self.manage_payments:
                    if mee == 'invoice':
                        inv_payments = all_payments.filtered(lambda payment: data.id in payment.reconciled_invoice_ids.ids)
                        self._manage_payment(inv_payments)
                    elif  mee == 'bills':
                        bill_payments = all_payments.filtered(lambda payment: data.id in payment.reconciled_bill_ids.ids)
                        self._manage_payment(bill_payments)
            if id_list:
                self._log(f'{len(id_list)} record(s) failed to export', type_=move_type, failed=id_list)
            if export_count:
                log_msg = f'{export_count} {move_type} exported'
                self._log(log_msg, type_=move_type, state='success')
                message = f'\n{log_msg}\n{message}'
            return message
        except Exception as e:
            self._log(e, type_=move_type)
            return f'\nExport {move_type} error:\n{e}\n'

    def _xero_invoice_cron(self):
        get_objects = self.env['sh.xero.configuration'].search([])
        for record in get_objects:
            if record.auto_import_invoice:
                record.invoice_import()
            if record.auto_export_invoice:
                record.invoice_export()
