# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import datetime
import re
from odoo import fields, models


class XeroProducts(models.Model):
    _inherit = 'sh.xero.configuration'

    import_products = fields.Boolean("Import Products")
    export_products = fields.Boolean("Export Products")
    auto_import_products = fields.Boolean("Auto Import Products")
    auto_export_products = fields.Boolean("Auto Export Products")
    last_sync_products = fields.Datetime("LS Products")

    def submit_products(self):
        if self.import_products:
            self.products_import()
        if self.export_products:
            self.final_product_export()

    def products_import(self):
        try:
            # params = {'page': 1}
            import_count = 0
            not_name = 0
            # while True:
            # success,response_json = self.get_req('Items', params=params)
            success,response_json = self.get_req('Items')
            if not success:
                return
            if not response_json.get('Items'):
                return
            for data in response_json['Items']:
                vals = {
                    'sh_xero_config': self.id,
                    'default_code': data['Code'] if data['Code'] else False,
                }
                # Required: name
                if data.get('Name'):
                    vals['name'] = data['Name']
                elif data.get('Code'):
                    vals['name'] = data['Code']
                else:
                    not_name += 1
                    continue
                if 'AccountCode' in data['PurchaseDetails']:
                    domain = [
                        ('code', '=', data['PurchaseDetails']['AccountCode'])]
                    get_acc = self.env['account.account'].search(domain)
                    if get_acc:
                        vals['property_account_expense_id'] = get_acc.id
                elif 'COGSAccountCode' in data['PurchaseDetails']:
                    domain = [
                        ('code', '=', data['PurchaseDetails']['COGSAccountCode'])]
                    get_acc = self.env['account.account'].search(domain)
                    if get_acc:
                        vals['property_account_expense_id'] = get_acc.id
                if 'AccountCode' in data['SalesDetails']:
                    domain = [
                        ('code', '=', data['SalesDetails']['AccountCode'])]
                    get_accs = self.env['account.account'].search(domain)
                    if get_accs:
                        vals['property_account_income_id'] = get_accs.id
                if 'TaxType' in data['SalesDetails'] and data['SalesDetails']['TaxType']:
                    domain = [('xero_tax_type', '=', data['SalesDetails']
                            ['TaxType']), ('type_tax_use', '=', 'sale')]
                    find_tax = self.env['account.tax'].search(domain)
                    if find_tax:
                        vals['taxes_id'] = find_tax.ids
                if 'TaxType' in data['PurchaseDetails'] and data['PurchaseDetails']['TaxType']:
                    domain = [('xero_tax_type', '=', data['PurchaseDetails']
                            ['TaxType']), ('type_tax_use', '=', 'purchase')]
                    find_tax = self.env['account.tax'].search(domain)
                    if find_tax:
                        vals['supplier_taxes_id'] = find_tax.ids
                if 'Description' in data:
                    vals['description_sale'] = data['Description'] if data['Description'] else False
                if 'PurchaseDescription' in data:
                    vals['description_purchase'] = data['PurchaseDescription'] if data['PurchaseDescription'] else False
                if data['IsSold']:
                    vals['sale_ok'] = True
                    if 'UnitPrice' in data['SalesDetails']:
                        vals['list_price'] = data['SalesDetails']['UnitPrice']
                else:
                    vals['sale_ok'] = False
                if data['IsPurchased']:
                    vals['purchase_ok'] = True
                    if 'UnitPrice' in data['PurchaseDetails']:
                        vals['standard_price'] = data['PurchaseDetails']['UnitPrice']
                else:
                    vals['purchase_ok'] = False
                if data['IsTrackedAsInventory']:
                    vals['type'] = 'product'
                domain = [('sh_xero_product_id', '=', data['ItemID'])]
                find_product = self.env['product.template'].search(domain)
                if find_product:
                    find_product.write(vals)
                else:
                    vals['sh_xero_product_id'] = data['ItemID']
                    self.env['product.template'].create(vals)
                import_count += 1
                # params['page'] += 1
            if not_name:
                self._log(f'Name not found for the {not_name} product(s)', type_='product')
            if import_count:
                self._log(f"{import_count} product(s) impoted/edited successfully", type_='product', state='success')
        except Exception as e:
            self._log(e, type_='product')

    def final_product_export(self):
        domain = [('sh_xero_config', '=', self.id)]
        if self.last_sync_products:
            domain.append(('write_date', '>', self.last_sync_products))
        get_products = self.env['product.template'].search(domain)
        if get_products:
            self.products_export(get_products)
        else:
            self._log("No New Products to Export", type_='product', state='success')

    def _export_product_tax(self, tax, check_tax):
        if tax and tax.xero_tax_type:
            if tax.xero_tax_type in check_tax:
                tax.write({
                    'name': tax.name + ' ',
                    'xero_tax_type': False,
                    'sh_xero_config': False,
                    'failure_reason': ''
                })
                self.wizard_tax_export(tax)

    def _product_vals(self, product, check_tax=False):
        # if product.sh_xero_product_id:
        #     continue
        desc = ''
        purchase_desc = ''
        if product.description:
            desc = re.sub(re.compile('<.*?>'), '', product.description)
        if product.description_purchase:
            purchase_desc = re.sub(re.compile('<.*?>'), '', product.description_purchase)
        if check_tax:
            self._export_product_tax(product.taxes_id, check_tax)
            # if product.taxes_id.xero_tax_type:
            #     if product.taxes_id.xero_tax_type in check_tax:
            #         # product.taxes_id.xero_tax_type = False
            #         # self.wizard_tax_export(product.taxes_id)
            self._export_product_tax(product.supplier_taxes_id, check_tax)
            # if product.supplier_taxes_id.xero_tax_type:
            #     if product.supplier_taxes_id.xero_tax_type in check_tax:
            #         # product.supplier_taxes_id.xero_tax_type = False
            #         # self.wizard_tax_export(product.supplier_taxes_id)
        sale_acc_code = ''
        if product.property_account_income_id:
            # if not (product.property_account_income_id.sh_xero_config and product.property_account_income_id.sh_xero_account_id):
            success,sale_acc_code = self._get_acc_code(product.property_account_income_id)
        purchase_acc_code = ''
        if product.property_account_expense_id:
            success,purchase_acc_code = self._get_acc_code(product.property_account_expense_id)
        vals = {
            'Name': product.name,
            'Code': product.default_code if product.default_code else product.name,
            'Description': desc,
            'PurchaseDescription': purchase_desc,
            'SalesDetails': {
                'UnitPrice': product.list_price,
                # 'AccountCode': product.property_account_income_id.code if product.property_account_income_id else '',
                'AccountCode': sale_acc_code,
                'TaxType': product.taxes_id.xero_tax_type if product.taxes_id.xero_tax_type else '',
            },
            'PurchaseDetails': {
                'UnitPrice': product.standard_price,
                'TaxType': product.supplier_taxes_id.xero_tax_type if product.supplier_taxes_id.xero_tax_type else '',
                # 'AccountCode': product.property_account_expense_id.code if product.property_account_expense_id else ''
                'AccountCode': purchase_acc_code
            }
        }
        if product.type == 'product':
            vals['IsTrackedAsInventory'] = True
        if product.sale_ok:
            vals['IsSold'] = True
        if product.purchase_ok:
            vals['IsPurchased'] = True
        if product.sh_xero_product_id and product.sh_xero_config:
            vals['ItemID'] = product.sh_xero_product_id
        return {"Items": [vals]}

    def _export_product(self, product, vals, count=0):
        success,response_json = self.post_req('Items', data=vals)
        if not success and 'TaxType' in response_json and not count:
            return self._export_product(product, self._product_vals(product, check_tax=response_json), 1)
        return success,response_json

    def _export_product_variant(self, product, tmpl):
        # if product.sh_xero_product_id:
        #     continue
        success,response_json = self._export_product(product, self._product_vals(product))
        if not success:
            product.write({'failure_reason': response_json})
            # id_list.append(str(product.id))
            return False
        # export_count += 1
        for vva in response_json['Items']:
            vra = {
                'sh_xero_product_id': vva['ItemID'],
                'sh_xero_config': self.id
            }
            tmpl.write(vra)
            product.write(vra)
        return True


    def products_export(self, get_products):
        try:
            export_count = 0
            id_list = []
            for tmpl in get_products:
                for product in tmpl.product_variant_ids:
                    # if product.sh_xero_product_id:
                    #     continue
                    if self._export_product_variant(product, tmpl):
                        export_count += 1
                    else:
                        id_list.append(str(product.id))
            msg_list = []
            if export_count:
                self._log(f"{export_count} product Exported Successfully", type_='product', state='success')
                msg_list.append(f"{export_count} product(variants) are exported")
            if id_list:
                self._log(f"{len(id_list)} product failed to export !", type_='product', failed=id_list)
                msg_list.append(f"{len(id_list)} product failed to export !")
            if not msg_list:
                msg_list.append('Product(s) are already synced')
            self.last_sync_products = datetime.now()
            return self._popup('Export Product', '\n\n'.join(msg_list))
        except Exception as e:
            self._log(e, type_='product')
            return self._popup('Export Product', str(e))


    def _xero_product_cron(self):
        domain = []
        get_objects = self.env['sh.xero.configuration'].search(domain)
        for record in get_objects:
            if record.auto_import_products:
                record.products_import()
            if record.auto_export_products:
                record.final_product_export()

    def create_xero_product(self):
        domain = [('name', '=', 'Xero Product')]
        pro = self.env['product.template'].search(domain)
        if not pro:
            vals = {
                'name': 'Xero Product',
                'type': 'product',
                'taxes_id': False,
                'supplier_taxes_id': False,
            }
            pro = self.env['product.template'].create(vals)
        return pro.product_variant_id
