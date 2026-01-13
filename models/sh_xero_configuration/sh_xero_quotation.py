# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import datetime
from odoo import fields, models
from odoo.tools import html2plaintext


class XeroQuotation(models.Model):
    _inherit = 'sh.xero.configuration'

    import_quotation = fields.Boolean("Import Quotation")
    export_quotation = fields.Boolean("Export Quotation")
    auto_import_quotation = fields.Boolean("Auto Import Quotation")
    auto_export_quotation = fields.Boolean("Auto Export Quotation")
    last_sync_quotation = fields.Datetime("LS Quotation")
    last_sync_import_quotation = fields.Date("Ls Import Quotation")
    page_count = fields.Integer("Page Count",default=1)

    def submit_quotation(self):
        if self.import_quotation:
            self.quotation_import()
        if self.export_quotation:
            self.final_quotation_export()

    # ------------------------------------------------
    #  Import Quotations From Xero
    # ------------------------------------------------

    def quotation_import(self):
        params = {'page': 1}
        if self.last_sync_import_quotation:
            date = datetime.strptime(str(self.last_sync_import_quotation), '%Y-%m-%d').date()
            params['where'] = f"Date>=DateTime('{date.year}, {date.month}, {date.day}')"
        import_count = 0
        while True:
            success,response_json = self.get_req('Quotes', params=params)
            if not success:
                # self.last_sync_import_quotation = datetime.today().strftime('%Y-%m-%d')
                break
            if not response_json.get('Quotes'):
                if params['page'] == 1:
                    self._log("There is no quotation to import !", type_='quotes', state='success')
                break
            for data in response_json['Quotes']:
                import_count += 1
                name = data['QuoteNumber'] if 'QuoteNumber' in data else "Quote"
                self._queue('quotation', data['QuoteID'], name)
            params['page'] += 1

        if import_count:
            self._log(f"{import_count} Quotation added to the queue", type_='quotes', state='success')
            self.last_sync_import_quotation = datetime.today().strftime('%Y-%m-%d')

    # ------------------------------------------------
    #  Loop 1 by 1 from Quotations queue to import
    # ------------------------------------------------

    def _loop_through_quote_queue(self, queue_recs):
        imported = failed = 0
        for queue in queue_recs:
            if queue.sh_id:
                try:
                    success,error = queue.sh_current_config.import_xero_quotation(queue)
                    if success:
                        imported += 1
                        queue._done()
                    else:
                        failed += 1
                        queue._error(error)
                except Exception as e:
                    failed += 1
                    queue._error(e)
            else:
                failed += 1
                queue._error('Not have the ID !')
        if imported:
            self._log(f'{imported} quotes imported from queue', type_='quotes', state='success')
        if failed:
            self._log(f'{failed} quotes failed to imported from queue', type_='quotes')

    # ------------------------------------------------
    #  Prepare Quotation Vals
    # ------------------------------------------------

    def _prepare_quote_vals(self, data):
        vals = {
            'sh_xero_config': self.id,
            # 'client_order_ref' : data['Reference'],
            'client_order_ref' : data.get('Reference'),
            'sh_xero_quote_number' : data['QuoteNumber'],
        }
        if data['Status'] == 'DRAFT':
            vals['state'] = 'draft'
        if 'Terms' in data:
            vals['note'] = data['Terms'] if data['Terms'] else ''
        domain = [('sh_xero_contact_id', '=', data['Contact']['ContactID'])]
        find_customer = self.env['res.partner'].search(domain,limit=1)
        if find_customer:
            vals['partner_id'] = find_customer.id
        else:
            self.create_emergency_contact(data['Contact']['ContactID'])
            domain = [('sh_xero_contact_id', '=', data['Contact']['ContactID'])]
            find_contact = self.env['res.partner'].search(domain,limit=1)
            if find_contact:
                vals['partner_id'] = find_contact.id
        if 'DateString' in data:
            start_date_last_sync = data['DateString'].split('T')[0]
            start_time_last_sync = data['DateString'].split('T')[1].split('.')[0]
            last_sync = start_date_last_sync + " " + start_time_last_sync
            final_last_sync = datetime.strptime(last_sync, '%Y-%m-%d %H:%M:%S')
            vals['date_order'] = final_last_sync
        if 'ExpiryDateString' in data:
            start_date_last_sync = data['ExpiryDateString'].split('T')[0]
            vals['validity_date'] = start_date_last_sync
        if 'CurrencyCode' in data:
            domain = [('name', '=', data['CurrencyCode'])]
            find_currency = self.env['res.currency'].search(domain)
            if find_currency:
                vals['currency_id'] = find_currency.id
        if 'LineItems' in data:
            list_of_order_lines = []
            for value in data['LineItems']:
                line_vals = {
                    'product_uom_qty' : value['Quantity'] if 'Quantity' in value and value['Quantity'] else 0,
                    'price_unit' : value['UnitAmount'] if 'UnitAmount' in value and value['UnitAmount'] else 0.0,
                }
                # if value.get('Description'):
                #     line_vals['name'] = value.get('Description') if value.get('Description') else find_pro.name
                if 'TaxType' in value and value['TaxType']:
                    domain = [('xero_tax_type', '=', value['TaxType']),('type_tax_use', '=', 'sale')]
                    find_tax = self.env['account.tax'].search(domain)
                    if find_tax:
                        line_vals['tax_id'] = find_tax.ids
                if value.get('ItemCode'):
                    domain = [('default_code', '=', value['ItemCode'])]
                    find_pro = self.env['product.product'].search(domain, limit=1)
                    if not find_pro:
                        self.products_import()
                        find_pro = self.env['product.product'].search(domain, limit=1)
                    line_vals['product_id'] = find_pro.id
                    line_vals.update({
                        'product_id': find_pro.id,
                        'name':  value.get('Description') if value.get('Description') else find_pro.name
                    })
                if 'tax_id' not in line_vals:
                    line_vals['tax_id'] = False
                domain = [('sh_xero_line_id', '=', value['LineItemID'])]
                find_line = self.env['sale.order.line'].search(domain)
                if find_line:
                    find_line.write(line_vals)
                else:
                    line_vals['sh_xero_line_id'] = value['LineItemID']
                    list_of_order_lines.append((0, 0, line_vals))
            vals['order_line'] = list_of_order_lines
        return vals

    # ------------------------------------------------
    #  Import Quotation From A Queue
    # ------------------------------------------------

    def import_xero_quotation(self, quote_queue):
        quotation = quote_queue.sh_id
        success,response_json = self.get_req('quotes_by_id', xero_id=quotation)
        if not success:
            return False, response_json
        # import_count = 0
        if not response_json.get('Quotes'):
            return False, 'Filed to get the quote data form xero !'
        if len(response_json['Quotes']) > 1:
            return False, 'Multiple quotes found for the same id !'
        # for data in response_json['Quotes']:
        data = response_json['Quotes'][0]
        vals = self._prepare_quote_vals(data)
        quotes = self.env['sale.order'].search([('sh_xero_quotation_id', '=', data['QuoteID'])])
        if quotes:
            quotes.write(vals)
        else:
            vals['sh_xero_quotation_id'] = data['QuoteID']
            quotes = self.env['sale.order'].create(vals)
        if data['Status'] == 'ACCEPTED':
            quotes.action_confirm()
        elif data['Status'] == 'DECLINED':
            quotes.action_cancel()
        quote_queue._done()
        return True, ''

    # ------------------------------------------------
    #  Export Quotations From Odoo to Xero
    # ------------------------------------------------

    def final_quotation_export(self):
        domain = [('state', '=', 'draft'), ('sh_xero_config', '=', self.id)]
        if self.last_sync_quotation:
            domain.append(('write_date', '>', self.last_sync_quotation))
        get_quotations = self.env['sale.order'].search(domain)
        if get_quotations:
            self.quotation_export(get_quotations)
        else:
            self._log("No New Quotations to Export", type_='quotes', state='success')

    # ------------------------------------------------
    #  Export Quotations
    # ------------------------------------------------

    def quotation_export(self, get_quotations):
        try:
            id_list = []
            export_count = 0
            for data in get_quotations:
                quote_date = ""
                validity_dates = ""
                if data.date_order:
                    quote_date = datetime.strftime(
                        data.date_order, "%Y-%m-%dT%H:%M:%SZ")
                if data.validity_date:
                    validity_dates = datetime.strftime(
                        data.validity_date, "%Y-%m-%dT00:00:00")
                vals = {
                    'Reference': data.client_order_ref if data.client_order_ref else "",
                    'Terms': html2plaintext(data.note) if data.note else "",
                    'DateString': quote_date,
                    'CurrencyCode': data.currency_id.name,
                    # 'CurrencyCode': 'AUD',
                }
                if validity_dates:
                    vals['ExpiryDateString'] = validity_dates
                # if not data.partner_id.sh_xero_contact_id:
                #     self.final_contact_export(data.partner_id)
                #     if not data.partner_id.sh_xero_contact_id:
                #         data.write({'failure_reason': 'Failed to find the contact for quotation'})
                #         id_list.append(str(data.id))
                #         continue
                # vals['Contact'] = {'ContactID': data.partner_id.sh_xero_contact_id}
                if data.partner_id.sh_xero_contact_id:
                    vals['Contact'] = {'ContactID': data.partner_id.sh_xero_contact_id}
                else:
                    if data.partner_id.parent_id:
                        domain = [('parent_id', '=', data.partner_id.parent_id.id)]
                    else:
                        domain = [('parent_id', '=', data.partner_id.id)]
                    get_cc_value = self.env['res.partner'].search(domain)
                    if get_cc_value:
                        for value in get_cc_value:
                            if value.sh_xero_contact_id:
                                vals['Contact'] = {'ContactID': value.sh_xero_contact_id}
                                break
                    if not vals.get('Contact'):
                        self.final_contact_export(data.partner_id)
                        if not data.partner_id.sh_xero_contact_id:
                            data.write({'failure_reason': 'Failed to find the contact for quotation'})
                            id_list.append(str(data.id))
                            continue
                        vals['Contact'] = {'ContactID': data.partner_id.sh_xero_contact_id}
                items = []
                if data.order_line:
                    for line in data.order_line:
                        if not line.product_id.sh_xero_product_id:
                            # need to export the line first ...
                            self._export_product_variant(line.product_id, line.product_id.product_tmpl_id)
                        line_vals = {
                            'Description': line.name,
                            'Quantity': line.product_uom_qty,
                            'UnitAmount': line.price_unit,
                            'ItemCode': line.product_id.default_code if line.product_id.default_code else line.product_id.name,
                        }
                        # if len(line.tax_id) > 1:
                        # elif line.tax_id.xero_tax_type:
                        #     line_vals['TaxType'] = line.tax_id.xero_tax_type
                        if len(line.tax_id) == 1:
                            if line.tax_id.xero_tax_type:
                                line_vals['TaxType'] = line.tax_id.xero_tax_type
                        if line.sh_xero_line_id:
                            line_vals['LineItemID'] = line.sh_xero_line_id
                        items.append(line_vals)
                    vals['LineItems'] = items
                if data.sh_xero_quotation_id:
                    vals['QuoteID'] = data.sh_xero_quotation_id
                request_body = {"Quotes": [vals]}
                success,response_json = self.post_req('Quotes', data=request_body, log=False)
                if not success:
                    data.write({'failure_reason': response_json})
                    id_list.append(str(data.id))
                    continue
                export_count += 1
                for vva in response_json['Quotes']:
                    data.write({
                        'sh_xero_quotation_id': vva['QuoteID'],
                        'sh_xero_quote_number': vva['QuoteNumber'],
                        'sh_xero_config': self.id,
                        'failure_reason': ''
                    })
                    if len(data.order_line) == 1:
                        for line in vva['LineItems']:
                            data.order_line.write({
                                'sh_xero_line_id': line['LineItemID']
                            })
                    elif len(data.order_line) >= 2:
                        for order_l in data.order_line:
                            for line in vva['LineItems']:
                                if line['UnitAmount'] == order_l.price_unit and line['ItemCode'] == order_l.product_id.default_code:
                                    line_vra = {
                                        'sh_xero_line_id': line['LineItemID']
                                    }
                                    order_l.write(line_vra)
            msg_list = []
            if id_list:
                self._log(f"{len(id_list)} quotation(s) failed to export !", type_='quotes', failed=id_list)
                msg_list.append(f"{len(id_list)} quotation(s) failed to export !")
            if export_count:
                self._log(f"{export_count} quotation(s) exported successfully", type_='quotes', state='success')
                msg_list.append(f"{export_count} quotation(s) exported successfully")
                self.last_sync_quotation = datetime.now()
            if not msg_list:
                msg_list.append('Quotations are already synced')
            return self._popup('Export Quotation', '\n\n'.join(msg_list))
        except Exception as e:
            self._log(e, type_='quotes')
            return self._popup('Export Quotation', str(e))

    # ------------------------------------------------
    #  Cron: Import Quotations From the queue
    # ------------------------------------------------

    def import_records_from_queue_quotation(self):
        get_queue = self.env['sh.xero.queue'].search([
            ('sh_current_state','=','draft'),
            ('queue_type', '=', 'quotation')
        ], limit=40)
        if get_queue:
            self._loop_through_quote_queue(get_queue)

    # ------------------------------------------------
    #  Cron: Export Quotations
    # ------------------------------------------------

    def _xero_quotation_cron(self):
        domain = []
        get_objects = self.env['sh.xero.configuration'].search(domain)
        for record in get_objects:
            if record.auto_import_quotation:
                record.quotation_import()
            if record.auto_export_quotation:
                record.final_quotation_export()
