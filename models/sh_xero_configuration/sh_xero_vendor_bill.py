# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import datetime
from odoo import fields, models


class XeroBill(models.Model):
    _inherit = 'sh.xero.configuration'

    import_bill = fields.Boolean("Import Vendor Bills")
    export_bill = fields.Boolean("Export Vendor Bills")
    auto_import_bill = fields.Boolean("Auto Import Bills")
    auto_export_bill = fields.Boolean("Auto Export Bills")
    last_sync_bill = fields.Datetime("LS Bills")
    last_sync_import_bill = fields.Date("LS Import Bills")

    def submit_bill(self):
        if self.import_bill:
            self.bill_import()
        if self.export_bill:
            self.bill_export()

    def bill_import(self):
        try:
            bill_type = 'Type=="ACCPAY"'
            params = {
                'page': 1,
                'where': bill_type
            }
            if self.last_sync_import_bill:
                date = datetime.strptime(str(self.last_sync_import_bill), '%Y-%m-%d').date()
                params['where'] = f'{bill_type} AND Date>=DateTime({date.year}, {date.month}, {date.day})'
            import_count = 0
            while True:
                success,response_json = self.get_req('bill', params=params)
                if not success:
                    break
                if not response_json.get('Invoices'):
                    break
                for data in response_json['Invoices']:
                    if data['Status'] in ('VOIDED', 'DELETED'):
                        continue
                    import_count += 1
                    sh_queue_name = data['InvoiceNumber'] if data.get('InvoiceNumber') else "Bill"
                    self._queue('bills', data['InvoiceID'], sh_queue_name)
                params['page'] += 1
            if import_count:
                self._log(f"{import_count} Bills added to the queue", type_='bill', state='success')
                self.last_sync_import_bill = datetime.today().strftime('%Y-%m-%d')
            else:
                self._log("Not find any new bills to import", type_='bill', state='success')
        except Exception as e:
            self._log(e, type_='bill', state='error')

    # --------------------------------------------
    #  Cron: Import Bills
    # --------------------------------------------

    def import_records_from_queue_bills(self):
        get_queue = self.env['sh.xero.queue'].search([
            ('sh_current_state','=','draft'),
            ('queue_type', '=', 'bills')
        ],limit=40)
        if not get_queue:
            get_queue = self.env['sh.xero.queue'].search([
                ('sh_current_state','=','error'),
                ('queue_type', '=', 'bills')
            ],limit=5)
            if not get_queue:
                return
        self._import_invoices(get_queue, 'in_invoice')

    def bill_export(self):
        try:
            domain = [('move_type', '=', 'in_invoice'),
                      ('sh_xero_config', '=', self.id)]
            if self.last_sync_bill:
                domain.append(('write_date', '>', self.last_sync_bill))
            get_bill = self.env['account.move'].search(domain)
            if get_bill:
                self.final_invoice_export(get_bill)
            else:
                self._log("No New Bills To Export", type_='bill', state='success')
        except Exception as e:
            self._log(e, type_='bill', state='error')

    def _xero_vendor_bill_cron(self):
        domain = []
        get_objects = self.env['sh.xero.configuration'].search(domain)
        for record in get_objects:
            if record.auto_import_bill:
                record.bill_import()
            if record.auto_export_bill:
                record.bill_export()
