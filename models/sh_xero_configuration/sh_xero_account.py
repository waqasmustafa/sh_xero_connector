# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


TYPE_DICT = {
    'asset_receivable': 'CURRENT',
    'asset_cash': 'BANK',
    'asset_current': 'CURRENT',
    'asset_non_current': 'NONCURRENT',
    'asset_prepayments': 'PREPAYMENT',
    'asset_fixed': 'FIXED',
    'liability_payable': "CURRLIAB",
    'liability_credit_card': "CURRLIAB",
    'liability_current': 'CURRLIAB',
    'liability_non_current': 'TERMLIAB',
    'equity': 'EQUITY',
    'equity_unaffected': 'EQUITY',
    'income': "REVENUE",
    'income_other': 'OTHERINCOME',
    'expense': 'EXPENSE',
    'expense_depreciation': 'DEPRECIATN',
    'expense_direct_cost': 'REVENUE',
    'off_balance': "",
}

ACC_TYPE = {
    'ASSET': 'asset_fixed',
    'EQUITY': 'equity',
    'EXPENSE': 'expense',
    'LIABILITY': 'liability_current',
    'REVENUE': 'expense'
}


class XeroAccount(models.Model):
    _inherit = 'sh.xero.configuration'

    import_account = fields.Boolean("Import Account")
    export_account = fields.Boolean("Export Account")
    auto_import_account = fields.Boolean("Auto Import Account")
    auto_export_account = fields.Boolean("Auto Export Account")
    # last_sync_account = fields.Datetime("LS Account")
    default_res_partner_bank_id = fields.Many2one('res.partner.bank', string='Default Bank (for account number when export the accounts)')

    def submit_account(self):
        if self.import_account:
            self.account_import()
        if self.export_account:
            self.final_account_export()

    def account_import(self):
        try:
            success,response_json = self.get_req('Accounts')
            if not success:
                self._log(response_json, type_='account')
                return
            if not response_json.get('Accounts'):
                self._log("Not find any account to import !", type_='account')
                return
            counter = 0
            for data in response_json['Accounts']:
                if data.get('BankAccountNumber'):
                    find_acc = self.env['res.partner.bank'].search([
                        ('acc_number', '=', data['BankAccountNumber'])])
                    if find_acc:
                        if not find_acc.sh_xero_account_id:
                            find_acc.sh_xero_account_id = data['AccountID']
                        continue
                    self._import_bank_acc(data)
                    counter += 1
                else:
                    find_acc = self.env['account.account'].search([
                        '|',
                        ('sh_xero_account_id', '=', data['AccountID']),
                        ('code', '=', data['Code'])
                    ])
                    if find_acc:
                        if not find_acc.sh_xero_account_id:
                            find_acc.sh_xero_account_id = data['AccountID']
                        if not find_acc.sh_xero_config:
                            find_acc.sh_xero_config = self.id
                        continue
                    self._import_coa(data)
                    counter += 1
            if counter:
                self._log(f"{counter} Account Impoted Successfully", type_='account', state='success')
            else:
                self._log("Already imported or No find any new account to import", type_='account', state='success')

            return
        except Exception as e:
            self._log(e, type_='account')
            return

    def _export_acc(self, vals):
        success,response_json = self.put_req('Accounts', data={'Accounts': [vals]}, log=False)
        where = False
        if 'unique Name' in response_json:
            where = f'Name="{vals["Name"]}"'
        elif 'unique Code' in response_json:
            where = f'Code="{vals["Code"]}"'
        if where:
            acc_success,acc_json = self.get_req('Accounts', params={'where': where})
            if acc_success:
                return acc_success,acc_json
        return success,response_json

    def _export_bank(self, find_banks):
        export_bank = 0
        name_covered = []
        for data in find_banks:
            if data.sh_xero_account_id:
                # export_bank += 1
                continue
            if not data.bank_name:
                continue
            if data.bank_name in name_covered:
                self._log(f"Bank '{data.bank_name}' Error: Please enter a unique Name !", type_='account')
                continue
            name_covered.append(data.bank_name)
            # request_body = {'Accounts': [{
            #     'Code': data.id,
            #     # 'Code': '4563245',
            #     'Name': data.bank_name,
            #     'Type': 'BANK',
            #     # 'BankAccountNumber': self.default_res_partner_bank_id.acc_number
            #     'BankAccountNumber': data.acc_number
            # }]}
            # success,response_json = self.put_req('Accounts', data=request_body, log=False)
            vals = {
                'Code': data.id,
                # 'Code': '4563245',
                'Name': data.bank_name,
                'Type': 'BANK',
                # 'BankAccountNumber': self.default_res_partner_bank_id.acc_number
                'BankAccountNumber': data.acc_number
            }
            success,response_json = self._export_acc(vals)
            if not success:
                self._log(f"Bank '{data.bank_name}' Error: {response_json}", type_='account')
                continue
            for value in response_json['Accounts']:
                data.write({
                    'sh_xero_account_id': value['AccountID']
                })  
            export_bank += 1
        if export_bank:
            self._log(f"{export_bank} bank(s) exported !", type_='account', state='success')

    def final_account_export(self):
        find_banks = self.env['res.partner.bank'].search([])
        if find_banks:
            self._export_bank(find_banks)
        get_account = self.env['account.account'].search([
            ('sh_xero_config', '=', self.id)])
        if get_account:
            return self.account_export(get_account)
        self._log("No New Accounts To Export", type_='account', state='success')
        return

    def _acc_vals(self, co_account):
        acc_name = co_account.name
        if co_account.search_count([('name', '=', co_account.name)]) > 1:
            acc_name = f"{co_account.code} {co_account.name}"
        vals = {
            'Code': co_account.code,
            'Name': acc_name,
            'Type': TYPE_DICT.get(co_account.account_type)
        }
        if vals.get('Type') == 'BANK':
            if not self.default_res_partner_bank_id:
                return False, 'Please set the default bank in the xero config !'
            if not self.default_res_partner_bank_id.acc_number:
                return False, 'Please set the account number in the default bank set in the xero config !'
            vals['BankAccountNumber'] = self.default_res_partner_bank_id.acc_number
        return True, vals

    def account_export(self, get_account, is_log=True):
        try:
            success_export_count = 0
            id_list = []
            already_exported = 0
            failed_reason = ''
            # co_account: Chart Of Account
            for co_account in get_account:
                # if co_account.sh_xero_account_id and co_account.sh_xero_config:
                #     already_exported += 1
                #     if co_account.failure_reasons:
                #         co_account.failure_reasons = ''
                #     continue
                val_get,vals = self._acc_vals(co_account)
                if not val_get:
                    id_list.append(str(co_account.id))
                    co_account.write({'failure_reasons': vals})
                    continue
                # request_body = {'Accounts': [vals]}
                # success,response_json = self.put_req('Accounts', data=request_body, log=False)
                success,response_json = self._export_acc(vals)
                if not success:
                    failed_reason = response_json
                    co_account.write({'failure_reasons': response_json})
                    id_list.append(str(co_account.id))
                    continue
                success_export_count += 1
                for value in response_json['Accounts']:
                    co_account.write({
                        'sh_xero_account_id': value['AccountID'],
                        'sh_xero_config': self.id,
                        'failure_reasons': ''
                    })
            msg_list = []
            if success_export_count:
                msg_list.append(f"{success_export_count} Account(s) exported successfully")
            # if already_exported:
            #     msg_list.append(f"{already_exported} Account(s) already exported")
            if is_log:
                if msg_list:
                    self._log(', '.join(msg_list), type_='account', state='success')
                elif not id_list and already_exported:
                    self._log("No more account(s) to exported", type_='account', state='success')
            if id_list:
                failed_log = f"{len(id_list)} Account(s) failed to export"
                if is_log:
                    self._log(failed_log, type_='account', failed=id_list)
                msg_list.append(failed_log)
            if not msg_list:
                msg_list.append('Accounts are already synced')
            if is_log:
                return self._popup('Export Account', '\n\n'.join(msg_list))
            return failed_reason
        except Exception as e:
            if is_log:
                self._log(e, type_='account')
            if is_log:
                return self._popup('Export Account', str(e))
            return str(e)


    def _xero_accounts_cron(self):
        get_objects = self.env['sh.xero.configuration'].search([])
        for record in get_objects:
            if record.auto_import_account:
                record.account_import()
            if record.auto_export_account:
                record.final_account_export()
