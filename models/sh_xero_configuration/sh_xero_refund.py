# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import datetime
from odoo import fields, models


class XeroRefund(models.Model):
    _inherit = 'sh.xero.configuration'

    import_refund = fields.Boolean("Import Refunds")
    export_refund = fields.Boolean("Export Refunds")
    auto_import_refund = fields.Boolean("Auto Import Refunds")
    auto_export_refund = fields.Boolean("Auto Export Refunds")
    last_sync_refund = fields.Datetime("LS Refund")
    last_sync_import_refund = fields.Date("Ls Import Refund")

    def submit_refund(self):
        if self.import_refund:
            self.refund_import()
        if self.export_refund:
            self.refund_export()

    def refund_import(self):
        try:
            debit_note_type = 'Type=="ACCPAYCREDIT"'
            params = {
                'page': 1,
                'where': debit_note_type
            }
            if self.last_sync_import_refund:
                date = datetime.strptime(str(self.last_sync_import_refund), '%Y-%m-%d').date()
                params['where'] = f'{debit_note_type} AND Date>=DateTime({date.year}, {date.month}, {date.day})'
            import_count = 0
            while True:
                success,response_json = self.get_req('vendor_refund', params=params)
                if not success:
                    break
                if not response_json.get('CreditNotes'):
                    break
                for data in response_json['CreditNotes']:
                    if data['Status'] == 'DELETED':
                        continue
                    import_count += 1
                    name = data['CreditNoteNumber'] if data.get('CreditNoteNumber') else "Debit Note"
                    self._queue('debit_note', data['CreditNoteID'], name)
                params['page'] += 1
            if import_count:
                self._log(f"{import_count} Debit Note added to the queue", type_='refund', state='success')
                self.last_sync_import_refund = datetime.today().strftime('%Y-%m-%d')
            else:
                self._log("Not find any new vendor refunt/debit note to import", type_='refund', state='success')
        except Exception as e:
            self._log(e, type_='refund')

    def refund_export(self):
        try:
            domain = [('sh_xero_config', '=', self.id), ('move_type', '=', 'in_refund')]
            if self.last_sync_refund:
                domain.append(('write_date', '>', self.last_sync_refund))
            find_credit = self.env['account.move'].search(domain)
            if find_credit:
                self.final_credit_note_export(find_credit, 'refund')
            else:
                self._log("No New Refunds To Export", type_='refund', state='success')
        except Exception as e:
            self._log(e, type_='refund')

    def _xero_vendor_refund_cron(self):
        domain = []
        get_objects = self.env['sh.xero.configuration'].search(domain)
        for record in get_objects:
            if record.auto_import_refund:
                record.refund_import()
            if record.auto_export_refund:
                record.refund_export()

    # ----------------------------------------------
    #  Cron: Import Debit Notes/ Vendor Refund
    # ----------------------------------------------

    def import_records_from_queue_debit_note(self):
        domain = [('sh_current_state','=','draft'),('queue_type', '=', 'debit_note')]
        get_queue = self.env['sh.xero.queue'].search(domain,limit=40)
        if not get_queue:
            domain = [('sh_current_state','=','error'),('queue_type', '=', 'debit_note')]
            get_queue = self.env['sh.xero.queue'].search(domain,limit=40)
            if not get_queue:
                return
        self._import_refund(get_queue, 'in_refund')
