# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.

from odoo import http
from odoo.http import request
import werkzeug
import werkzeug.utils

class Main(http.Controller):

    @http.route('/home/xero', type='http', auth="public")
    def o_auth(self, **kwargs):
        if kwargs['code']:
            get_config = request.env['sh.xero.configuration'].sudo().search([
                ('id','=',kwargs['state'])],limit=1)
            vals = {
                'code' : kwargs['code'],
                'received_code' : True
            }
            get_config.write(vals)
            get_config.generate_token()
        return werkzeug.utils.redirect("/")
