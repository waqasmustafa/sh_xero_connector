# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class PartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    sh_xero_account_id = fields.Char('Xero Account Id', copy=False)


class ContactXero(models.Model):
    _inherit = 'res.partner'

    sh_xero_contact_id = fields.Char("Xero Contacts", copy=False)
    sh_xero_config = fields.Many2one(
        'sh.xero.configuration', string="Xero Config", copy=False)
    main_person = fields.Boolean("Main Person", copy=False)
    failure_reasons = fields.Char("Failure Reasons", copy=False)

    def export_xero_contact(self):
        active_partner_ids = self.env['res.partner'].browse(
            self.env.context.get('active_ids'))
        domain = [('company_id', '=', self.env.user.company_id.id)]
        find_config = self.env['sh.xero.configuration'].search(domain)
        return find_config.final_contact_export(active_partner_ids)
