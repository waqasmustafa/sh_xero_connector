# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import datetime
import json
import requests
from requests.auth import HTTPBasicAuth
from odoo import fields, models, api, _
from odoo.exceptions import UserError

TIMEOUT = 30
API = {
    'ManualJournals': 'ManualJournals',
    'journal_by_id': 'ManualJournals/%s',

    'Quotes': 'Quotes',
    'quotes_by_id': 'Quotes/%s',

    'CreditNotes': 'CreditNotes',
    'credit_note_by_id': 'CreditNotes/%s',

    'vendor_refund': 'CreditNotes',

    'Invoices': 'Invoices',
    'invoice_by_id': 'Invoices/%s',

    'TaxRates': 'TaxRates',

    'bill': 'Invoices',

    'Payments': 'Payments',

    'Prepayments': 'Prepayments',
    'prepayments_by_id': 'Prepayments/%s/Allocations',

    'Overpayments': 'Overpayments',
    'overpayments_by_id': 'Overpayments/%s/Allocations',

    'Contacts': 'Contacts',
    'contact_by_id': 'Contacts?IDs=%s',

    'PurchaseOrders': 'PurchaseOrders',
    'purchase_by_id': 'PurchaseOrders/%s',

    'Accounts': 'Accounts',
    'Organisation': 'Organisation',
    'Items': 'Items'
}

LOG_TYPE = {
    'Quotes': 'quotes',
    'CreditNotes': 'credit_note',
    'Invoices': 'invoice',
    'TaxRates': 'tax',
    'bill': 'bill',
    'Payments': 'payment',
    'Prepayments': 'payment',
    'Overpayments': 'payment',
    'Contacts': 'contact',
    'vendor_refund': 'refund',
    'Items': 'product',
    'PurchaseOrders': 'purchase',
    'Accounts': 'account'
}


class XeroConfiguration(models.Model):
    _name = "sh.xero.configuration"
    _description = "Stores Your Xero Configuration"

    user_id = fields.Many2one(
        'res.users', string='User', required=True, default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company)
    name = fields.Char("Name")
    client_id = fields.Char("Client ID")
    client_secret = fields.Char("Client Secret")
    redirect_url = fields.Char("Redirect Url")
    code = fields.Char("Code")
    received_code = fields.Boolean("Received")
    xero_logger_id = fields.One2many(
        'sh.xero.log', 'sh_xero_id', string="Log History")
    refresh_token = fields.Char("Refresh Token")
    access_token = fields.Char("Access Token")
    tenant_id = fields.Char("Tenant Id")
    link = fields.Char("Link", compute="_compute_get_link",
                       default="Click the link generated here")

    # -------------------------------------------------------
    #  Create a queue obj
    # -------------------------------------------------------

    def _queue(self, queue_type, sh_id, sh_queue_name):
        find_queue = self.env['sh.xero.queue'].search([
            ('sh_id', '=', sh_id),
            ('queue_type', '=', queue_type)
        ], limit=1)
        if find_queue:
            if find_queue.sh_current_state != 'draft':
                find_queue._draft()
            return find_queue
        return self.env['sh.xero.queue'].create({
            'queue_sync_date': datetime.now(),
            'sh_current_config' : self.id,
            'sh_current_state': 'draft',
            'queue_type': queue_type,
            'sh_id': sh_id,
            'sh_queue_name': sh_queue_name,
        })

    # -------------------------------------------------------
    #  Xero Pop-up
    # -------------------------------------------------------

    def _popup(self, title, message):
        view = self.env.ref("sh_xero_connector.sh_xero_popup")
        context = dict(self._context or {})
        context["message"] = message
        return {
            "name": title,
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "sh.xero.popup",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "context": context,
        }

    # -------------------------------------------------------
    #  Create the log
    # -------------------------------------------------------

    def _log(self, message, type_='purchase', state='error', failed=False):
        self.env['sh.xero.log'].create({
            "name": self.name,
            "sh_xero_id": self.id,
            "datetime": datetime.now(),
            "failed_list": ','.join(failed) if failed else False,
            "state": state,
            "type_": type_,
            "error": message
        })

    # -------------------------------------------------------
    #  Get Failure Reason
    # -------------------------------------------------------

    def _get_reason(self, response):
        if response.status_code == 429:
            return 'Too many requests, Please try after some time !'
        if response.status_code == 401 and 'TokenExpired' in response.text:
            if self._refresh_cred():
                return 'Please try after some time !'
            else:
                return 'Token Expired, Please regenerate the token in the Xero Credentials !'
        json_data = {}
        try:
            json_data = response.json()
        except:
            return f'Failed to get the response from Xero,\n{response.text}'
        msg_list = []
        if json_data.get('Message'):
            msg_list.append(json_data['Message'])
            # return json_data['Message']
        if json_data.get('Elements'):
            for rec in json_data['Elements']:
                if rec.get('ValidationErrors'):
                    for vall in rec['ValidationErrors']:
                        msg_list.append(vall['Message'])
                elif rec.get('AuthorisationError'):
                    msg_list.append(rec['AuthorisationError']['Message'])
        if msg_list:
            return ', '.join(msg_list)
        return f'Failed to get the response from Xero,\n{response.text}'

    # -------------------------------------------------------
    #  Make Request
    # -------------------------------------------------------

    def _make_req(self, req, endpoint, xero_id=False, params=False, data=False, log=True):
        # global API, LOG_TYPE
        url = 'https://api.xero.com/api.xro/2.0/' + API.get(endpoint)
        if xero_id:
            url = url % (xero_id)
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.access_token}',
            'Xero-Tenant-Id': self.tenant_id
        }
        response = False
        try:
            if req == 'get':
                if not params:
                    params = {}
                response = requests.get(url=url, headers=headers, params=params, timeout=TIMEOUT)
            elif req == 'post':
                response = requests.post(url=url, headers=headers, data=data, timeout=TIMEOUT)
            elif req == 'put':
                response = requests.put(url=url, headers=headers, data=data, timeout=TIMEOUT)
        except requests.exceptions.RequestException as e:
            return False, 'Error: The request failed or timed out !'

        if response.status_code == 200:
            return True, response.json()

        reason = self._get_reason(response)

        if not xero_id and LOG_TYPE.get(endpoint) and log:
            self._log(reason, type_=LOG_TYPE[endpoint])

        return False, reason

    # -------------------------------------------------------
    #  API Request
    # -------------------------------------------------------

    def get_req(self, endpoint, xero_id=False, params=False, log=True):
        return self._make_req('get', endpoint, xero_id=xero_id, params=params, log=log)

    def update_req(self, req, endpoint, data, xero_id=False, log=True):
        if not data:
            return False, 'Failed to get the data !'
        if endpoint in ('ManualJournals', 'Payments'):
            data=json.dumps(data, default=str)
        else:
            data=json.dumps(data)
        return self._make_req(req, endpoint, data=data, xero_id=xero_id, log=log)

    def post_req(self, endpoint, data, xero_id=False, log=True):
        return self.update_req('post', endpoint, data=data, xero_id=xero_id, log=log)

    def put_req(self, endpoint, data, xero_id=False, log=True):
        return self.update_req('put', endpoint, data=data, xero_id=xero_id, log=log)

    # -------------------------------------------------------
    #  ORM Method
    # -------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("company_id", False):
                domain = [('company_id.id', '=', vals['company_id'])]
                already = self.search(domain)
                if already:
                    raise UserError(
                        _("One Company is allowed to have one Credentials"))
        res = super(XeroConfiguration, self).create(vals_list)
        return res

    def _compute_get_link(self):
        if self.client_id and self.redirect_url:
            url = f"https://login.xero.com/identity/connect/authorize?response_type=code&client_id={self.client_id}&redirect_uri={self.redirect_url}&scope=offline_access accounting.transactions accounting.contacts accounting.settings&state={self.id}"
            self.link = url

    def generate_token(self):
        token_url = "https://identity.xero.com/connect/token"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        params = {
            'grant_type': 'authorization_code',
            'code': self.code,
            'redirect_uri': self.redirect_url,
        }
        response = requests.post(url=token_url, headers=headers, auth=HTTPBasicAuth(
            self.client_id, self.client_secret), data=params)
        if response.status_code != 200:
            # raise UserError(_('Failed to get the response from the xero !'))
            return
        response_json = response.json()
        self.access_token = response_json['access_token']
        self.refresh_token = response_json['refresh_token']
        self.get_tenant()

    def generate_refresh_token(self):
        refresh_url = "https://identity.xero.com/connect/token"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        params = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        response = requests.post(url=refresh_url, headers=headers, auth=HTTPBasicAuth(
            self.client_id, self.client_secret), data=params)
        if response.status_code != 200:
            raise UserError(_('Failed to get the response from the xero !'))
        response_json = response.json()
        self.access_token = response_json['access_token']
        self.refresh_token = response_json['refresh_token']

    def _refresh_cred(self):
        refresh_url = "https://identity.xero.com/connect/token"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        params = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        response = requests.post(
            url=refresh_url,
            headers=headers,
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
            data=params
        )
        if response.status_code != 200:
            # invalid_grant
            if response.status_code == 400:
                self.received_code = False
            return False
        response_json = response.json()
        # record.access_token = response_json['access_token']
        # record.refresh_token = response_json['refresh_token']
        self.write({
            'access_token': response_json['access_token'],
            'refresh_token': response_json['refresh_token']
        })
        return True


    def _cron_refresh_token(self):
        get_objects = self.env['sh.xero.configuration'].search([])
        for record in get_objects:
            record._refresh_cred()

    def get_tenant(self):
        tenant_url = "https://api.xero.com/connections"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + str(self.access_token),
        }
        response = requests.get(url=tenant_url, headers=headers)
        if response.status_code != 200:
            return
        response_json = response.json()
        for data in response_json:
            self.write({'tenant_id': data['tenantId']})

    def _get_acc_code(self, account_id):
        xero_acc_config = self.env['sh.xero.account.config'].search([
            ('sh_odoo_acc_id', '=', account_id.id)
        ], limit=1)
        if xero_acc_config:
            if xero_acc_config.sh_xero_acc_id:
                return True, xero_acc_config.sh_xero_acc_id.code

        if not (account_id.sh_xero_account_id and account_id.sh_xero_config):
            self.account_export(account_id, is_log=False)
            if not account_id.sh_xero_account_id:
                # return False, f"Failed to find the account '{account_id.name} [{account_id.code}]' on Xero \nYou can map it with Xero account in 'Account Config'"
                return False, f"Export account '{account_id.name} [{account_id.code}]' Error: {message}"

        return True, account_id.code
