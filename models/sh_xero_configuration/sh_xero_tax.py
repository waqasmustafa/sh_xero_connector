# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class XeroTax(models.Model):
    _inherit = 'sh.xero.configuration'

    import_tax = fields.Boolean("Import Tax")
    export_tax = fields.Boolean("Export Tax")
    auto_import_tax = fields.Boolean("Auto Import Tax")
    auto_export_tax = fields.Boolean("Auto Export Tax")
    # last_sync_tax = fields.Datetime("LS Tax")
    xero_country_id = fields.Many2one('res.country')
    sh_tax_group_id = fields.Many2one('account.tax.group', string='Tax Group')

    def submit_tax(self):
        if self.import_tax:
            self.tax_import()
        if self.export_tax:
            self.tax_export()


    def tax_import(self):
        try:
            if not self.sh_tax_group_id:
                self._log('Please select the tax group !', type_='tax')
                return
            success,response_json = self.get_req('TaxRates')
            if not success:
                return
            if not response_json.get('TaxRates'):
                self._log("Not find any tax to import", type_='tax', state='success')
                return

            if not self.xero_country_id:
                self.get_xero_organization_details()
                if not self.xero_country_id:
                    self._log('Failed to get the country !', type_='tax')
                    return
            count = already_imported = 0
            for data in response_json['TaxRates']:
                if self.env['account.tax'].search([('xero_tax_type', '=', data['TaxType'])]):
                    already_imported += 1
                    continue
                count += 1
                group_vals = {
                    'name': data['Name'],
                    'sh_xero_config': self.id,
                    'amount_type': 'percent',
                    'type_tax_use': 'sale',
                    'xero_tax_type': data['TaxType'],
                    'amount': data['EffectiveRate'],
                    # 'country_id': self.xero_country_id.id,
                    'country_id': self.sh_tax_group_id.country_id.id,
                    'tax_group_id': self.sh_tax_group_id.id
                }
                self.env['account.tax'].create(group_vals)
                group_vals['type_tax_use'] = 'purchase'
                self.env['account.tax'].create(group_vals)
            message = ''
            if count:
                message = f'{count} tax imported'
            elif already_imported:
                message = f'{already_imported} tax already imported'
            self._log(message, type_='tax', state='success')
        except Exception as e:
            self._log(e, type_='tax')

    def get_xero_organization_details(self):
        success,response_json = self.get_req('Organisation')
        if not success:
            return
        for data in response_json['Organisations']:
            domain = ['|', ('name', '=', data['CountryCode']),
                      ('code', '=', data['CountryCode'])]
            find_country = self.env['res.country'].search(domain)
            if find_country:
                self.xero_country_id = find_country

    # =========================================
    #  Export
    # =========================================

    def tax_export(self):
        get_tax = self.env['account.tax'].search([
            ('children_tax_ids', '!=', False),
            ('sh_xero_config', '=', self.id)
        ])
        if get_tax:
            self._export_tax(get_tax, is_parent=True, ssr=1)
        else:
            self._log("No New Tax To Export", type_='tax', state='success')

    def _prepare_tax_vals(self, tax, is_parent=False, tax_covered_list=False):
        if is_parent:
            vals = {'Name': tax.name}
            tax_comp = []
            for child_tax in tax.children_tax_ids:
                if child_tax.name not in tax_covered_list:
                    tax_covered_list.append(child_tax.name)
                vall = {
                    'Name': child_tax.name,
                    'Rate': child_tax.amount,
                }
                if child_tax.include_base_amount:
                    vall['IsCompound'] = True
                else:
                    vall['IsCompound'] = False
                tax_comp.append(vall)
            if tax_comp:
                vals['TaxComponents'] = tax_comp
            return {"TaxRates": [vals]}
        return {
            "TaxRates": [{
                'Name': tax.name,
                # Tax Types – can only be used on update calls
                # 'TaxType': tax.xero_tax_type,
                'ReportTaxType': 'OUTPUT',
                'TaxComponents': [{
                    'Name': tax.name,
                    'Rate': tax.amount,
                    'IsCompound': tax.include_base_amount,
                    # 'TaxType': tax.xero_tax_type,
                }]
            }]
        }

    def _export_filter_tax(self, all_tax, is_parent=False):
        tax_covered_list = []
        id_list = []
        exported = 0
        alredy_on_xero = 0
        # System defined Tax Rates cannot be updated
        for tax in all_tax:
            if tax.sh_xero_config:
                alredy_on_xero += 1
                continue
            if is_parent and tax.name in tax_covered_list:
                continue
            tax_covered_list.append(tax.name)
            request_body = self._prepare_tax_vals(tax, is_parent=is_parent, tax_covered_list=tax_covered_list)
            success,response_json = self.post_req('TaxRates', data=request_body, log=False)
            if not success:
                tax.write({'failure_reason': response_json})
                id_list.append(str(tax.id))
                continue
            exported += 1
            for vva in response_json['TaxRates']:
                vvas = {
                    'xero_tax_type': vva['TaxType'],
                    'sh_xero_config': self.id
                }
                tax.write(vvas)
                find_same = self.env['account.tax'].search([
                    ('name', '=', tax.name)])
                for xxy in find_same:
                    xxy.write(vvas)
        return exported, alredy_on_xero, tax_covered_list, id_list

    def _export_tax(self, all_tax, is_parent=False, ssr=2):
        try:
            exported, alredy_on_xero, tax_covered_list, id_list = self._export_filter_tax(all_tax, is_parent=is_parent)
            if is_parent and ssr == 1:
                geet_tax = self.env['account.tax'].search([
                    ('name', 'not in', tax_covered_list), ('sh_xero_config', '=', self.id)])
                if geet_tax:
                    self._export_filter_tax(geet_tax)
            msg_list = []
            if id_list:
                self._log(f"{len(id_list)} tax failed to export !", type_='tax', failed=id_list)
                msg_list.append(f'{len(id_list)} tax failed to export')
            if exported:
                self._log(f"{exported} tax exported successfully", type_='tax', state='success')
                msg_list.append(f"{exported} tax exported successfully")
            if alredy_on_xero:
                msg_list.append(f"{alredy_on_xero} tax already on xero")
            if not msg_list:
                msg_list.append('Tax are synced')
            # return self._popup('Export Tax', '\n\n'.join(msg_list))
            return '\n\n'.join(msg_list)
        except Exception as e:
            self._log(e, type_='tax')
            # return self._popup('Export Tax', str(e))
            return f'\n\n{str(e)}'

    def wizard_tax_export(self, get_tax):
        parent_tax_list = []
        tax_list = []
        group_tax_count = 0
        for data in get_tax:
            if data.amount_type == 'group':
                group_tax_count += 1
                continue
            if data.children_tax_ids:
                parent_tax_list.append(data)
            else:
                tax_list.append(data)
        message = ''
        if parent_tax_list:
            message += self._export_tax(parent_tax_list, is_parent=True)
        if tax_list:
            message += self._export_tax(tax_list)
        if group_tax_count:
            message += f'{group_tax_count} group tax are not exported on Xero'
        if not message:
            message = 'Tax are exported'
        return self._popup('Export Tax', message)

    # =========================================
    #  Cron
    # =========================================

    def _xero_tax_cron(self):
        domain = []
        get_objects = self.env['sh.xero.configuration'].search(domain)
        if not get_objects:
            return
        for record in get_objects:
            if record.auto_import_tax:
                record.tax_import()
            if record.auto_export_tax:
                record.tax_export()
