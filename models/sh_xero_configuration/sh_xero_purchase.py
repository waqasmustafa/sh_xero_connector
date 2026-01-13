# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import datetime
from odoo import fields, models


class XeroPurchase(models.Model):
    _inherit = 'sh.xero.configuration'

    import_purchase = fields.Boolean("Import Purchase Orders")
    export_purchase = fields.Boolean("Export Purchase Orders")
    auto_import_purchase = fields.Boolean("Auto Import Purchase Orders")
    auto_export_purchase = fields.Boolean("Auto Export Purchase Orders")
    last_sync_purchase = fields.Datetime("LS Purchase Orders")
    purchase_import_use = fields.Selection(
        [('rfq', 'RFQ'), ('po', 'Purchase Order')], default="rfq", string="Import As")
    last_sync_import_purchase = fields.Date('LS Import Purchase')

    def submit_purchase(self):
        if self.import_purchase:
            self.purchase_import()
        if self.export_purchase:
            self.final_purchase_export()

    def purchase_import(self):
        try:
            params = {'page': 1}
            if self.last_sync_import_purchase:
                date = datetime.strptime(str(self.last_sync_import_purchase), '%Y-%m-%d').date()
                params['where'] = f"Date>=DateTime('{date.year}, {date.month}, {date.day}')"
            import_count = 0
            while True:
                success,response_json = self.get_req('PurchaseOrders', params=params)
                if not success:
                    break
                if not response_json.get('PurchaseOrders'):
                    break
                for data in response_json['PurchaseOrders']:
                    import_count += 1
                    name = data['PurchaseOrderNumber'] if 'PurchaseOrderNumber' in data else "Purchase Order"
                    self._queue('purchase_order', data['PurchaseOrderID'], name)
                params['page'] += 1
            if import_count:
                self._log(f"{import_count} Purchase Order added to the queue", state='success')
                self.last_sync_import_purchase = datetime.today().strftime('%Y-%m-%d')
            else:
                self._log("Not find any more purchase order to import", state='success')
        except Exception as e:
            self._log(e)

    # ----------------------------------------
    #  CRON: Import Purchase Orders
    # ----------------------------------------

    def import_records_from_queue_purchase(self):
        domain = [('sh_current_state','=','draft'),('queue_type', '=', 'purchase_order')]
        get_queue = self.env['sh.xero.queue'].search(domain,limit=40)
        if not get_queue:
            domain = [('sh_current_state','=','error'),('queue_type', '=', 'purchase_order')]
            get_queue = self.env['sh.xero.queue'].search(domain,limit=5)
            if not get_queue:
                return
        self.manually_from_queue_purchase(get_queue)

    # ----------------------------------------
    #  Loop through purchase queue to import
    # ----------------------------------------

    def manually_from_queue_purchase(self,records):
        if not records:
            return
        failed = imported = 0
        for queue in records:
            if not queue.sh_id:
                queue._error('Not has Xero ID !')
                failed += 1
                continue
            success,reason = queue.sh_current_config.import_xero_purchase(queue.sh_id)
            if success:
                queue._done()
                imported += 1
            else:
                queue._error(reason)
                failed += 1
        if failed:
            self._log(f"{failed} purchase order(s) Failed to Imported From Queue")
        if imported:
            self._log(f"{imported} purchase order(s) Imported Successfully From Queue", state='success')

    # -------------------------------------
    #  Prepare Purchase Vals
    # -------------------------------------

    def _prepare_purchase_vals(self, data):
        vals = {
            'partner_ref' : data['Reference'] if data['Reference'] else False,
            'sh_xero_config' : self.id,
            'sh_xero_purchase_number' : data['PurchaseOrderNumber']
        }
        domain = [('sh_xero_contact_id', '=', data['Contact']['ContactID'])]
        find_contact = self.env['res.partner'].search(domain, limit=1)
        if not find_contact:
            self.create_emergency_contact(data['Contact']['ContactID'])
            find_contact = self.env['res.partner'].search(domain, limit=1)
            if not find_contact:
                return False, 'Failed to get the partner/contact !'
        vals['partner_id'] = find_contact.id
        if 'DateString' in data:
            start_date_last_sync = data['DateString'].split('T')[0]
            start_time_last_sync = data['DateString'].split('T')[1].split('.')[0]
            last_sync = start_date_last_sync + " " + start_time_last_sync
            final_last_sync = datetime.strptime(last_sync, '%Y-%m-%d %H:%M:%S')
            vals['date_planned'] = final_last_sync
        if 'DeliveryDateString' in data:
            start_date_last_syncs = data['DeliveryDateString'].split('T')[0]
            start_time_last_syncs = data['DeliveryDateString'].split('T')[1].split('.')[0]
            last_syncs = start_date_last_syncs + " " + start_time_last_syncs
            final_last_syncs = datetime.strptime(last_syncs, '%Y-%m-%d %H:%M:%S')
            vals['date_order'] = final_last_syncs
        if 'CurrencyCode' in data:
            domain = [('name', '=', data['CurrencyCode'])]
            find_currency = self.env['res.currency'].search(domain)
            if find_currency:
                vals['currency_id'] = find_currency.id
        if data.get('LineItems'):
            list_of_order_lines = []
            for value in data['LineItems']:
                line_vals = {
                    'product_qty' : value['Quantity'],
                }
                if 'UnitAmount' in value:
                    line_vals['price_unit'] = value['UnitAmount']
                if 'DiscountRate' in value:
                    line_vals['discount'] = value['DiscountRate'] if value['DiscountRate'] else ''
                product_name = ''
                if 'Description' in value and value['Description']:
                    product_name = value['Description']
                    if ']' in product_name:
                        product_name = product_name.split(']')[1].strip()
                    line_vals['name'] = product_name
                if 'TaxType' in value and value['TaxType']:
                    find_tax = self.env['account.tax'].search([
                        ('xero_tax_type', '=', value['TaxType']),('type_tax_use', '=', 'purchase')])
                    if find_tax:
                        line_vals['taxes_id'] = find_tax.ids
                if value.get('ItemCode'):
                    find_pro = self.env['product.product'].search([
                        ('default_code', '=', value['ItemCode'])], limit=1)
                    if not find_pro:
                        find_pro = self.env['product.template'].create({
                            'name': product_name,
                            'type': 'product',
                            'taxes_id': False,
                            'supplier_taxes_id': False,
                        }).product_variant_id
                        find_pro.write({
                            'default_code': value['ItemCode']
                        })
                else:
                    find_pro = self.create_xero_product()
                if find_pro:
                    line_vals['product_id'] = find_pro.id
                if 'taxes_id' not in line_vals:
                    line_vals['taxes_id'] = False
                domain = [('sh_xero_purchase_line_id', '=', value['LineItemID'])]
                find_line = self.env['purchase.order.line'].search(domain)
                if find_line:
                    find_line.write(line_vals)
                else:
                    line_vals['sh_xero_purchase_line_id'] = value['LineItemID']
                    list_of_order_lines.append((0, 0, line_vals))
            vals['order_line'] = list_of_order_lines
        return vals, ''

    # -------------------------------------
    #  Import Purchase From Queue
    # -------------------------------------

    def import_xero_purchase(self,xero_id):
        success,response_json = self.get_req('purchase_by_id', xero_id=xero_id)
        if not success:
            return False, response_json
        if not response_json.get('PurchaseOrders'):
            return False, 'Failed to get the data !'
        if len(response_json['PurchaseOrders']) > 1:
            return False, 'Get multiple records for the same xero ID !'
        data = response_json['PurchaseOrders'][0]
        vals,vals_reason = self._prepare_purchase_vals(data)
        if not vals:
            return False, vals_reason
        purchase_order = self.env['purchase.order'].search([
            ('sh_xero_purchase_id', '=', data['PurchaseOrderID'])])
        if purchase_order:
            purchase_order.write(vals)
        else:
            vals['sh_xero_purchase_id'] = data['PurchaseOrderID']
            purchase_order = self.env['purchase.order'].create(vals)
        if self.purchase_import_use == 'po':
            purchase_order.button_confirm()
        return True, ''

    def final_purchase_export(self):
        domain = [('state', '=', 'draft'), ('sh_xero_config', '=', self.id)]
        if self.last_sync_purchase:
            domain.append(('write_date', '>', self.last_sync_purchase))
        get_po = self.env['purchase.order'].search(domain)
        if get_po:
            self.purchase_export(get_po)
        else:
            self._log("No New Quotations to Export", state='success')

    def purchase_export(self, get_po):
        try:
            id_list = []
            export_count = 0
            for po in get_po:
                po_date = ""
                validity_dates = ""
                if po.date_planned:
                    po_date = datetime.strftime(po.date_planned, "%Y-%m-%dT%H:%M:%SZ")
                if po.date_order:
                    validity_dates = datetime.strftime(po.date_order, "%Y-%m-%dT%H:%M:%SZ")
                vals = {
                    'DateString': po_date if po_date else "",
                    'DeliveryDateString': validity_dates if validity_dates else '',
                    'Reference': po.partner_ref if po.partner_ref else '',
                    'CurrencyCode': po.currency_id.name,
                    # 'CurrencyCode': 'AUD',
                }
                if po.partner_id.sh_xero_contact_id:
                    vals['Contact'] = {
                        'ContactID': po.partner_id.sh_xero_contact_id
                    }
                else:
                    # if po.partner_id.parent_id:
                    #     domain = [('parent_id', '=', po.partner_id.parent_id.id)]
                    # else:
                    #     domain = [('parent_id', '=', po.partner_id.id)]
                    # find_partner = self.env['res.partner'].search(domain)
                    # if find_partner:
                    #     for partner in find_partner:
                    #         if partner.sh_xero_contact_id:
                    #             vals['Contact'] = {'ContactID': partner.sh_xero_contact_id}
                    #             break
                    # Export the partner on xero,
                    # to export the po
                    self.final_contact_export(po.partner_id)
                    vals['Contact'] = {'ContactID': po.partner_id.sh_xero_contact_id}
                items = []
                if po.order_line:
                    for line in po.order_line:
                        if not line.product_id.sh_xero_product_id:
                            # need to export the line first ...
                            self._export_product_variant(line.product_id, line.product_id.product_tmpl_id)
                        line_vals = {
                            'Description': line.name,
                            'Quantity': line.product_qty,
                            'UnitAmount': line.price_unit,
                            'ItemCode': line.product_id.default_code if line.product_id.default_code else line.product_id.name,
                            'AccountCode': line.product_id.property_account_expense_id.code,
                            'DiscountRate': line.discount if line.discount else '',
                        }
                        # if len(line.taxes_id) > 1:
                        #     # export_count += 1
                        #     # failed_list.append(str(po.id))
                        #     failed_list.append(po.name)
                        #     id_list.append(str(po.id))
                        # elif line.taxes_id.xero_tax_type:
                        #     line_vals['TaxType'] = line.taxes_id.xero_tax_type
                        if len(line.taxes_id) == 1:
                            if line.taxes_id.xero_tax_type:
                                line_vals['TaxType'] = line.taxes_id.xero_tax_type
                        if line.sh_xero_purchase_line_id:
                            line_vals['LineItemID'] = line.sh_xero_purchase_line_id
                        items.append(line_vals)
                    vals['LineItems'] = items
                if po.sh_xero_purchase_id:
                    vals['PurchaseOrderID'] = po.sh_xero_purchase_id
                request_body = {"PurchaseOrders": [vals]}
                success,response_json = self.post_req('PurchaseOrders', data=request_body)
                if not success:
                    po.write({'failure_reasons': response_json})
                    # failed_list.append(po.name)
                    id_list.append(str(po.id))
                    continue
                export_count += 1
                for vva in response_json['PurchaseOrders']:
                    vra = {
                        'sh_xero_purchase_id': vva['PurchaseOrderID'],
                        'sh_xero_purchase_number': vva['PurchaseOrderNumber'],
                        'sh_xero_config': self.id,
                        'failure_reasons': ''
                    }
                    po.write(vra)
                    if len(po.order_line) == 1:
                        for line in vva['LineItems']:
                            line_vra = {'sh_xero_purchase_line_id': line['LineItemID']}
                            po.order_line.write(line_vra)
                    elif len(po.order_line) >= 2:
                        for line in vva['LineItems']:
                            for order_l in po.order_line:
                                if line['UnitAmount'] == order_l.price_unit and line['ItemCode'] == order_l.product_id.default_code:
                                    line_vra = {'sh_xero_purchase_line_id': line['LineItemID']}
                                    order_l.write(line_vra)
            msg_list = []
            if id_list:
                self._log(f"{len(id_list)} purchase order(s) failed to export", failed=id_list)
                msg_list.append(f"{len(id_list)} purchase order(s) failed to export")
            if export_count:
                self._log(f"{export_count} purchase order(s) are exported successfully", state='success')
                msg_list.append(f"{export_count} purchase order(s) are exported successfully")
            if not msg_list:
                msg_list.append('Purchase order(s) are already synced')
            self.last_sync_purchase = datetime.now()
            return self._popup('Export Purchase Order', '\n\n'.join(msg_list))
        except Exception as e:
            self._log(e)
            return self._popup('Export Purchase Order', str(e))

    def _xero_purchase_cron(self):
        domain = []
        get_objects = self.env['sh.xero.configuration'].search(domain)
        for record in get_objects:
            if record.auto_import_purchase:
                record.purchase_import()
            if record.auto_export_purchase:
                record.final_purchase_export()
