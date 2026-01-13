# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import datetime
from odoo import fields, models, _
from odoo.exceptions import UserError


class XeroManualJournal(models.Model):
    _inherit = 'sh.xero.configuration'

    import_journal = fields.Boolean("Import Manual Journal")
    export_journal = fields.Boolean("Export Manual Journal")
    auto_import_journal = fields.Boolean("Auto Import Journal")
    auto_export_journal = fields.Boolean("Auto Export Journal")
    last_sync_journal = fields.Datetime("LS Journal")
    default_manual_journal = fields.Many2one('account.journal', domain=[('type', '=', 'general')], string='Manual Journal')
    # last_sync_import_journal = fields.Date('LS Import Journal')
    # narration = fields.Char('Narration')

    def submit_journal(self):
        if self.import_journal:
            if not self.default_manual_journal:
                raise UserError(_("Please select Default Manual Journal"))
            self.journal_import()
        if self.export_journal:
            self.journal_export()

    def journal_import(self):
        try:
            success,response_json = self.get_req('ManualJournals')
            if not success:
                self._log(response_json, type_='journal')
                return
            if not response_json.get('ManualJournals'):
                self._log("No Manual Journal To Import", type_='journal', state='success')
                return
            import_count = 0
            for data in response_json['ManualJournals']:
                name = data.get('Narration') if data.get('Narration') else "Journal"
                if name == 'MISC/2023/12/0001':
                    continue
                import_count += 1
                self._queue('journal', data['ManualJournalID'], name)
            if import_count:
                self._log(f'{import_count} journal(s) added in the queue', type_='journal', state='success')
                # self.last_sync_import_journal = datetime.today().strftime('%Y-%m-%d')
            else:
                self._log('Not find any data to import', type_='journal', state='success')
        except Exception as e:
            self._log(e, type_='journal')

    def _import_journal(self, queue):
        success,reason = self.final_journal_import(queue)
        if success:
            return success,reason
        if 'is not balanced' in reason:
            return self.final_journal_import(queue)
        return success,reason

    def final_journal_import(self, queue):
        try:
            if self.env['account.move'].search([('sh_xero_manual_journal_id', '=', queue.sh_id)]):
                return True, ''
            success,response_json = self.get_req('journal_by_id', queue.sh_id)
            if not success:
                return False, response_json
            if not response_json.get('ManualJournals'):
                return False, "Failed to get the data !"
            if len(response_json['ManualJournals']) > 1:
                return False, 'Get multiple records from xero for the same id !'
            data = response_json['ManualJournals'][0]
            vals = {
                'ref': data['Narration'],
                'move_type': 'entry',
                'journal_id': self.default_manual_journal.id,
            }
            pay_date = self.compute_date(data['Date'])
            pay_dates = pay_date.split('T')
            final_date = datetime.strptime(pay_dates[0], '%Y-%m-%d')
            vals['date'] = final_date
            if data.get('JournalLines'):
                line_list = []
                not_account_id = False
                for x_line in data['JournalLines']:
                    if not x_line.get('AccountID'):
                        not_account_id = True
                        break
                    get_account = self.env['account.account'].search([
                        ('sh_xero_account_id', '=', x_line['AccountID'])
                    ], limit=1)
                    if get_account:
                        line_vals = {'account_id': get_account.id}
                        if x_line.get('Description'):
                            line_vals['name'] = x_line['Description']
                        if x_line['LineAmount'] > 0:
                            line_vals['debit'] = x_line['LineAmount']
                        else:
                            line_vals['credit'] = abs(x_line['LineAmount'])
                        line_list.append((0, 0, line_vals))
                if not_account_id:
                    return False, "Line in xero has no account id !"
                if line_list:
                    vals['line_ids'] = line_list
            vals['sh_xero_manual_journal_id'] = queue.sh_id
            create_entry = self.env['account.move'].create(vals)
            if data['Status'] == 'POSTED':
                create_entry.action_post()
            return True, ''
        except Exception as e:
            return False, str(e)

    # --------------------------------------------
    #  Cron: Import Journal
    # --------------------------------------------

    def _cron_import_journals_from_queue(self):
        find_config = self.env['sh.xero.configuration'].search([('company_id', '=', self.env.user.company_id.id)],limit=1)
        if not find_config:
            return
        domain = [('sh_current_state','=','draft'),('queue_type', '=', 'journal')]
        get_queue = self.env['sh.xero.queue'].search(domain,limit=30)
        if not get_queue:
            domain = [('sh_current_state','=','error'),('queue_type', '=', 'journal')]
            get_queue = self.env['sh.xero.queue'].search(domain,limit=1)
            if not get_queue:
                return
        find_config._import_journals_from_queue(get_queue)

    # --------------------------------------------
    #  Import Journal
    # --------------------------------------------

    def _import_journals_from_queue(self, journal_queues):
        failed = imported = 0
        for queue in journal_queues:
            if not queue.sh_id:
                queue._error('Not has Xero ID !')
                failed += 1
                continue
            success,reason = self._import_journal(queue)
            if success:
                queue._done()
                imported += 1
            else:
                queue._error(reason)
                failed += 1
        if failed:
            self._log(f"{failed} journal(s) Failed to Imported From Queue", type_='journal')
        if imported:
            self._log(f"{imported} journal(s) Imported Successfully From Queue", type_='journal', state='success')

    # --------------------------------------------
    #  Export Journal
    # --------------------------------------------

    def journal_export(self):
        # domain = [('journal_id.type', '=', 'general')]
        domain = [('move_type', '=', 'entry')]
        if self.last_sync_journal:
            domain.append(('write_date', '>', self.last_sync_journal))
        journal_entries = self.env['account.move'].search(domain)
        if journal_entries:
            self.final_journal_export(journal_entries)
        else:
            self._log("No Manual Journal To Export", type_='journal', state='success')

    # def send_manual_journal(self, data):
    #     if data.sh_xero_manual_journal_id:
    #         return
    #     vals = {
    #         'Narration': data.name,
    #         'Date': data.invoice_date,
    #     }
    #     if data.state == 'draft':
    #         vals['Status'] = 'DRAFT'
    #     if data.state == 'posted':
    #         vals['status'] = 'POSTED'
    #     line_list = []
    #     line_vals = {
    #         'Description': data.line_ids[len(data.line_ids)-2].name,
    #         'AccountCode': data.line_ids[len(data.line_ids)-2].account_id.code,
    #     }
    #     if data.line_ids[len(data.line_ids)-2].credit != 0:
    #         line_vals['LineAmount'] = - \
    #             (data.line_ids[len(data.line_ids)-2].credit)
    #     else:
    #         line_vals['LineAmount'] = data.line_ids[len(data.line_ids)-2].debit
    #     line_list.append(line_vals)
    #     line_vals = {
    #         'Description': data.line_ids[len(data.line_ids)-1].name,
    #         'AccountCode': data.line_ids[len(data.line_ids)-1].account_id.code,
    #     }
    #     if data.line_ids[len(data.line_ids)-1].credit != 0:
    #         line_vals['LineAmount'] = - \
    #             (data.line_ids[len(data.line_ids)-1].credit)
    #     else:
    #         line_vals['LineAmount'] = data.line_ids[len(data.line_ids)-1].debit
    #     line_list.append(line_vals)
    #     vals['JournalLines'] = line_list
    #     request_body = {'ManualJournals': [vals]}
    #     count = 0
    #     success,response_json = self.post_req('ManualJournals', data=request_body)
    #     if not success:
    #         count += 1
    #         data.write({'failure_reason': response_json})
    #         return
    #     for rec in response_json['ManualJournals']:
    #         data.write({'sh_xero_manual_journal_id': rec['ManualJournalID']})
    #     self.last_sync_journal = datetime.now()

    def _prepare_export_journal_vals(self, journal_entry):
        narration = journal_entry.ref if journal_entry.ref else journal_entry.name
        if not narration:
            reason = "please provide the reference/narration"
            journal_entry.write({'failure_reason': reason})
            return False, f"{journal_entry.name}\n {reason}"
        vals = {
            'Narration': narration,
            'Date': journal_entry['date'],
        }
        if journal_entry.state == 'draft':
            vals['Status'] = 'DRAFT'
        if journal_entry.state == 'posted':
            vals['status'] = 'POSTED'
        line_list = []
        failure_reason = False
        for line in journal_entry.line_ids:
            # account_code = False
            success,account_code = self._get_acc_code(line.account_id)
            if not success:
                failure_reason = account_code
                break
            # xero_acc_config = self.env['sh.xero.account.config'].search([
            #     ('sh_odoo_acc_id', '=', line.account_id.id)
            # ])
            # if xero_acc_config:
            #     if xero_acc_config.sh_xero_acc_id:
            #         account_code = xero_acc_config.sh_xero_acc_id.code

            # if not account_code:
            #     if not line.account_id.sh_xero_account_id:
            #     #     account_code = line.account_id.code
            #     # else:
            #         self.account_export(line.account_id, is_log=False)
            #         if not line.account_id.sh_xero_account_id:
            #             failure_reason = f'{line.account_id.name} [{line.account_id.code}]'
            #             break
            #     account_code = line.account_id.code

            line_vals = {
                'Description': line.name,
                'AccountCode': account_code
            }
            if line.credit != 0:
                line_vals['LineAmount'] = -(line.credit)
            else:
                line_vals['LineAmount'] = line.debit

            # if not line.tax_ids:
            #     line_vals['TaxType'] = 'BASEXCLUDED'
                # line_vals['TaxAmount'] = 0.0
            line_list.append(line_vals)
        if failure_reason:
            # failed_reason = f"{journal_entry.name}\n{failure_reason}"
            journal_entry.write({'failure_reason': failure_reason})
            # self._log(failed_reason, type_='journal')
            return False, f"{journal_entry.name}\n{failure_reason}"

        if line_list:
            vals['JournalLines'] = line_list

        return vals,''

    def final_journal_export(self, journal_entries):
        try:
            export_count = 0
            already_exported = 0
            message = ''
            id_list = []
            for journal_entry in journal_entries:
                # if journal_entry.journal_id.type == 'general':
                if journal_entry.sh_xero_manual_journal_id:
                    already_exported += 1
                    continue

                vals,failed_reason = self._prepare_export_journal_vals(journal_entry)
                if not vals:
                    message += f"\n{failed_reason}\n"
                    id_list.append(str(journal_entry.id))
                    continue

                request_body = {'ManualJournals': [vals]}
                success,response_json = self.post_req('ManualJournals', data=request_body, log=False)
                if not success:
                    failed_reason = f"{journal_entry.name}\nError: {response_json}"
                    journal_entry.write({'failure_reason': response_json})
                    # self._log(failed_reason, type_='journal')
                    message += f"\n{failed_reason}\n"
                    id_list.append(str(journal_entry.id))
                    continue
                export_count += 1
                for rec in response_json['ManualJournals']:
                    journal_entry.write({
                        'sh_xero_manual_journal_id': rec['ManualJournalID'],
                        'sh_xero_config': self.id,
                        'failure_reason': ''
                    })

            if id_list:
                self._log(f'{id_list} records failed to export !', type_='journal', failed=id_list)

            log_msg_list = []
            if export_count:
                log_msg_list.append(f'{export_count} Journal(s) successfully exported')
            if already_exported:
                log_msg_list.append(f'{already_exported} Journal(s) already synced')

            if log_msg_list:
                success_msg = ', '.join(log_msg_list)
                self._log(success_msg, type_='journal', state='success')
                message += f'\n{success_msg}\n'
            return message
        except Exception as e:
            self._log(e, type_='journal')
            return str(e)


    def _xero_manual_journal_cron(self):
        domain = []
        get_objects = self.env['sh.xero.configuration'].search(domain)
        for record in get_objects:
            if record.auto_import_journal:
                record.journal_import()
            if record.auto_export_journal:
                record.journal_export()
