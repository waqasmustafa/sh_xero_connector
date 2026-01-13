# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import datetime
from odoo import fields, models


class XeroContacts(models.Model):
    _inherit = 'sh.xero.configuration'

    import_contact = fields.Boolean("Import Contacts")
    export_contact = fields.Boolean("Export Contacts")
    auto_import_contact = fields.Boolean("Auto Import Contacts")
    auto_export_contact = fields.Boolean("Auto Export Contacts")
    last_sync_contact = fields.Datetime("LS Contact")

    def submit_contact(self):
        if self.import_contact:
            self.contact_import()
        if self.export_contact:
            self.contact_export()

    def contact_import(self):
        try:
            params = {'page': 1}
            while True:
                success,response_json = self.get_req('Contacts', params=params)
                if not success:
                    break
                if not response_json.get('Contacts'):
                    if params['page'] == 1:
                        self._log("No Contacts to Import", type_='contact', state='success')
                    break
                for data in response_json['Contacts']:
                    self.generate_contact_vals(data)
                self._log(f"{len(response_json['Contacts'])} Contact(s) Impoted/Edited Successfully", type_='contact', state='success')
                params['page'] += 1
        except Exception as e:
            self._log(e, type_='contact')

    def create_emergency_contact(self, partner):
        success,response_json = self.get_req('contact_by_id', xero_id=partner)
        if not success:
            self._log(response_json, type_='contact')
            return
        if not response_json.get('Contacts'):
            self._log("No Contacts to Import", type_='contact', state='success')
            return
        for data in response_json['Contacts']:
            self.generate_contact_vals(data)
        self._log("Impoted Successfully", type_='contact', state='success')

    def generate_contact_vals(self, data):
        vals = {}
        names = ''
        if 'LastName' in data and data['LastName']:
            if 'FirstName' in data and data['FirstName']:
                names = data['FirstName'] + ' ' + data['LastName']
            else:
                names = data['LastName']
        else:
            if 'FirstName' in data and data['FirstName']:
                names = data['FirstName']
            elif 'LastName' in data:
                names = data['LastName']
                vals['sh_lastname'] = data['LastName'] if data['LastName'] else False
        if names:
            if 'Website' in data:
                vals['website'] = data['Website'] if data['Website'] else False
            if 'TaxNumber' in data:
                vals['vat'] = data['TaxNumber'] if data['TaxNumber'] else False
            vals = {
                'main_person': True,
                'name': names,
                'company_type': 'person',
                'sh_xero_config': self.id,
                'sh_firstname': data['FirstName'] if 'FirstName' in data and data['FirstName'] else False,
                'email': data['EmailAddress'] if 'EmailAddress' in data and data['EmailAddress'] else False,
            }
            if 'PurchasesDefaultAccountCode' in data:
                domain = [('code', '=', data['PurchasesDefaultAccountCode'])]
                find_purchase_account = self.env['account.account'].search(
                    domain)
                if find_purchase_account:
                    # domain = [('name', '=', 'Payable')]
                    # fin = self.env['account.account.type'].search(domain)
                    # vaa = {
                    #     'user_type_id': fin.id,
                    #     'reconcile': True
                    # }
                    # find_purchase_account.write(vaa)
                    vals['property_account_payable_id'] = find_purchase_account.id
            from_where = 'inside'
            # company = self.check_company(data,from_where)
            # if company:
            #     vals['parent_id'] = company.id
            if 'SalesDefaultAccountCode' in data:
                domain = [('code', '=', data['SalesDefaultAccountCode'])]
                find_sales_account = self.env['account.account'].search(domain)
                if find_sales_account:
                    #     domain = [('name', '=', 'Receivable')]
                    #     fin = self.env['account.account.type'].search(domain)
                    #     vaa = {
                    #         'user_type_id': fin.id,
                    #         'reconcile': True
                    #     }
                    #     find_sales_account.write(vaa)
                    vals['property_account_receivable_id'] = find_sales_account.id
            if 'ContactPersons' in data:
                for vv_con in data['ContactPersons']:
                    if 'LastName' in vv_con and vv_con['LastName']:
                        if vv_con['FirstName'] and vv_con['LastName']:
                            namess = vv_con['FirstName'] + \
                                ' ' + vv_con['LastName']
                    else:
                        if vv_con['FirstName']:
                            namess = vv_con['FirstName']
                        elif 'LastName' in data:
                            namess = vv_con['LastName']
                    domain = [('name', '=', namess)]
                    already_contact = self.env['res.partner'].search(domain)
                    if not already_contact:
                        domain = [('name', '=', data['Name']),
                                  ('is_company', '=', True)]
                        find_company = self.env['res.partner'].search(domain)
                        con_vals = {
                            'sh_xero_config': self.id,
                            'name': namess,
                            'sh_firstname': vv_con['FirstName'] if vv_con['FirstName'] else False,
                            'sh_lastname': vv_con['LastName'] if vv_con['LastName'] else False,
                            'email': vv_con['EmailAddress'] if vv_con['EmailAddress'] else False,
                        }
                        if find_company:
                            con_vals['parent_id'] = find_company.id
                        self.env['res.partner'].create(con_vals)
            if 'Addresses' in data:
                for value in data['Addresses']:
                    if value['AddressType'] == 'STREET':
                        if 'City' in value:
                            vals['city'] = value['City'] if value['City'] else False
                        if 'PostalCode' in value:
                            vals['zip'] = value['PostalCode'] if value['PostalCode'] else False
                        if 'AttentionTo' in value:
                            vals['street'] = value['AttentionTo'] if value['AttentionTo'] else False
                        if 'Region' in value:
                            if value['Region']:
                                domain = [
                                    '|', ('name', '=', value['Region']), ('code', '=', value['Region'])]
                                state = self.env['res.country.state'].search(
                                    domain, limit=1)
                                if state:
                                    vals['state_id'] = state.id
                                    vals['country_id'] = state.country_id.id
            if 'Phones' in data:
                for value in data['Phones']:
                    if value['PhoneType'] == 'DEFAULT':
                        if 'PhoneNumber' in value:
                            number = value.get(
                                'PhoneCountryCode', '')+value.get('PhoneAreaCode', '')+value.get('PhoneNumber', '')
                            vals['phone'] = number
                    if value['PhoneType'] == 'MOBILE':
                        if 'PhoneNumber' in value:
                            mobile = value.get(
                                'PhoneCountryCode', '')+value.get('PhoneAreaCode', '')+value.get('PhoneNumber', '')
                            vals['phone'] = mobile
            domain = [('sh_xero_contact_id', '=', data['ContactID'])]
            find_contact = self.env['res.partner'].search(domain, limit=1)
            if find_contact:
                find_contact.write(vals)
            else:
                vals['sh_xero_contact_id'] = data['ContactID']
                self.env['res.partner'].create(vals)
        else:
            from_where = 'outside'
            self.check_company(data, from_where)

    def check_company(self, data, from_where):
        # domain = [('name', '=', data['Name']), ('is_company', '=', True)]
        # find_parent = self.env['res.partner'].search(domain, limit=1)
        company = ''
        comp_vals = {
            'sh_xero_config': self.id,
            'name': data['Name'],
            'company_type': 'company',
        }
        if 'TaxNumber' in data:
            comp_vals['vat'] = data['TaxNumber'] if data['TaxNumber'] else False
        if 'PurchasesDefaultAccountCode' in data:
            find_purchase_account = self.env['account.account'].search([
                ('code', '=', data['PurchasesDefaultAccountCode'])])
            if find_purchase_account:
                # domain = [('name', '=', 'Payable')]
                # fin = self.env['account.account.type'].search(domain)
                # vaa = {
                #     'user_type_id': fin.id,
                #     'reconcile': True
                # }
                # find_purchase_account.write(vaa)
                comp_vals['property_account_payable_id'] = find_purchase_account.id
        if 'SalesDefaultAccountCode' in data:
            domain = [('code', '=', data['SalesDefaultAccountCode'])]
            find_sales_account = self.env['account.account'].search(domain)
            if find_sales_account:
                # domain = [('name', '=', 'Receivable')]
                # fin = self.env['account.account.type'].search(domain)
                # vaa = {
                #     'user_type_id': fin.id,
                #     'reconcile': True
                # }
                # find_sales_account.write(vaa)
                comp_vals['property_account_receivable_id'] = find_sales_account.id
        if from_where == 'outside':
            domain = [('sh_xero_contact_id', '=', data['ContactID'])]
            find_contact = self.env['res.partner'].search(domain, limit=1)
            if not find_contact:
                comp_vals['sh_xero_contact_id'] = data['ContactID']
                create_company = self.env['res.partner'].create(comp_vals)
                company = create_company
            else:
                find_contact.write(comp_vals)
                company = find_contact
        elif from_where == 'inside':
            domain = [('sh_xero_contact_id', '=', data['ContactID'])]
            find_contact = self.env['res.partner'].search(domain, limit=1)
            if not find_contact:
                create_company = self.env['res.partner'].create(comp_vals)
                company = create_company
        return company

    def contact_export(self):
        domain = [('sh_xero_config', '=', self.id)]
        if self.last_sync_contact:
            domain.append(('write_date', '>', self.last_sync_contact))
        get_contacts = self.env['res.partner'].search(domain)
        if get_contacts:
            self.final_contact_export(get_contacts)
        else:
            self._log("No New Contacts To Export", type_='contact', state='success')

    def _quick_export_contact(self, partner):
        if self.call_export_contact(partner, self.contact_generate_vals(partner)):
            return True
        return False

    def final_contact_export(self, get_contacts):
        try:
            id_list = []
            for partner in get_contacts:
                if partner.company_type == 'person':
                    if partner.parent_id:
                        self.check_childs(partner)
                    else:
                        vals = self.contact_generate_vals(partner)
                        if not self.call_export_contact(partner, vals):
                            id_list.append(str(partner.id))
                else:
                    if not partner.child_ids:
                        vals = self.contact_generate_vals(partner)
                        if not self.call_export_contact(partner, vals):
                            id_list.append(str(partner.id))
                    else:
                        self.check_childs(partner)
                if not partner.sh_xero_contact_id:
                    vals = self.contact_generate_vals(partner)
                    if self.call_export_contact(partner, vals):
                        id_list.append(str(partner.id))
            msg = ''
            if id_list:
                msg = f"{len(id_list)} contact(s) failed to export"
                self._log(msg, type_='contact', failed=id_list)
            else:
                msg = f"{len(get_contacts)} contact(s) exported/edited"
                self._log(msg, type_='contact', state='success')
                self.last_sync_contact = datetime.now()
            return self._popup('Export Purchase Order', msg)
        except Exception as e:
            self._log(e, type_='contact')
            return self._popup('Export Contact', str(e))

    def check_childs(self, partner):
        if partner.parent_id:
            find_comp = partner.parent_id
        else:
            find_comp = partner
        main_person_count = 0
        contact_person = []
        xero_limit = 0
        for rec in find_comp.child_ids:
            if not rec.main_person:
                if xero_limit == 5:
                    continue
                xero_limit += 1
                pra = {
                    'FirstName': rec.sh_firstname if rec.sh_firstname else rec.name,
                    'LastName': rec.sh_lastname if rec.sh_lastname else '',
                    'EmailAddress': rec.email if rec.email else ''
                }
                contact_person.append(pra)
            if rec.main_person:
                main_person_count += 1
        if main_person_count != 0:
            for rec in find_comp.child_ids:
                if rec.main_person:
                    vals = self.contact_generate_vals(rec)
                    if contact_person:
                        vals['ContactPersons'] = contact_person
                    self.call_export_contact(rec, vals)
                    rec.write({'main_person': True})
        elif partner.email:
            vals = self.contact_generate_vals(partner)
            if contact_person:
                vals['ContactPersons'] = contact_person
            self.call_export_contact(partner, vals)
            partner.write({'main_person': True})

    def contact_generate_vals(self, partner):
        if partner.street and partner.street2:
            streets = f'{partner.street} {partner.street2}'
        else:
            streets = partner.street
        address = [
            {
                "AddressType": "STREET",
                "City": partner.city if partner.city else "",
                "PostalCode": partner.zip if partner.zip else "",
                "Region": partner.state_id.name if partner.state_id else "",
                "Country": partner.country_id.name if partner.country_id else "",
                "AttentionTo": streets,
            }
        ]
        phone = [
            {
                "PhoneType": "DEFAULT",
                "PhoneNumber": partner.phone if partner.phone else ""
            },
            {
                "PhoneType": "MOBILE",
                "PhoneNumber": partner.mobile if partner.mobile else ""
            }
        ]
        vals = {
            'Name': partner.parent_id.name if partner.parent_id else partner.name,
            'FirstName': partner.sh_firstname if partner.sh_firstname else partner.name,
            'LastName': partner.sh_lastname if partner.sh_lastname else "",
            'EmailAddress': partner.email if partner.email else "",
            'Website': partner.website if partner.website else "",
            'Addresses': address,
            'Phones': phone,
            'TaxNumber': partner.vat if partner.vat else '',
            # 'PurchasesDefaultAccountCode' : partner.property_account_payable_id.code if partner.property_account_payable_id else '',
            # 'SalesDefaultAccountCode' : partner.property_account_receivable_id.code if partner.property_account_receivable_id else '',
        }
        return vals

    def call_export_contact(self, data, vals):
        if data.sh_xero_contact_id:
            vals['ContactId'] = data.sh_xero_contact_id
        request_body = {"Contacts": [vals]}
        success,resp_json = self.post_req('Contacts', data=request_body)
        if not success:
            data.write({'failure_reasons': resp_json})
            return False
        for ids in resp_json['Contacts']:
            ids_vals = {
                'sh_xero_contact_id': ids['ContactID'],
                'sh_xero_config': self.id
            }
            data.write(ids_vals)
            if data.child_ids:
                for value in data.child_ids:
                    value.write({'sh_xero_config': self.id})
            elif data.parent_id:
                data.parent_id.write({'sh_xero_config': self.id})
                domain = [('parent_id', '=', data.parent_id.id)]

                find_brothers = self.env['res.partner'].search(domain)
                if find_brothers:
                    for brother in find_brothers:
                        brother.write({'sh_xero_config': self.id})
        return True


    def _xero_contact_cron(self):
        get_objects = self.env['sh.xero.configuration'].search([])
        for record in get_objects:
            if record.auto_import_contact:
                record.contact_import()
            if record.auto_export_contact:
                record.contact_export()
