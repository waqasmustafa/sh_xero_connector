# Part of Softhealer Technologies.
{
    "name": "Xero Odoo Connector | Xero-Odoo Connector [OAuth2.0]",
    "author": "Softhealer Technologies",
    "version": "18.0.0.01",
    "license": "OPL-1",
    "category": "Extra Tools",
    "summary": "Connect xero with Odoo xero Connector xero Odoo Integration Xero sync Xero Connector with REST API xero accounting Odoo xero integration odoo xero accounting integration sync data between zero and odoo integrate XERO with ODOO OAuth 2.0 xero connectors Odoo Connectors Odoo xero to odoo integration xero Import xero export",
    "description": """Xero is a cloud-based small business accounting software with tools for managing invoicing, bank reconciliation, purchasing and more. It is a modern, small business accounting software that lives in the cloud. Odoo is a much bigger than the xero. Using this application you can sync your xero data with odoo in one click.""",
    "depends": ['base', 'sale_management', 'contacts', 'sh_first_last_name', 'purchase', 'stock'],
    "data": [
        # security
        "security/ir.model.access.csv",
        "security/sh_xero_connector_groups.xml",
        # wizard
        "wizard/sh_xero_popup_views.xml",
        # data
        "data/account_account_data.xml",
        "data/account_move_data.xml",
        "data/account_payment_data.xml",
        "data/product_template_data.xml",
        "data/purchase_order_data.xml",
        "data/res_partner_data.xml",
        "data/sale_order_data.xml",
        "data/sh_xero_queue_data.xml",
        "data/account_tax_data.xml",
        "data/ir_cron_data.xml",
        # views
        "views/sh_xero_configuration_views.xml",
        "views/sh_xero_account_config_views.xml",
        "views/sh_xero_queue_views.xml",
        "views/res_partner_views.xml",
        "views/sale_order_views.xml",
        "views/account_tax_views.xml",
        "views/purchase_order_views.xml",
        "views/product_template_views.xml",
        "views/product_product_views.xml",
        "views/account_move_views.xml",
        "views/account_account_views.xml",
        "views/account_payment_views.xml",
        # Menus
        "views/sh_xero_configuration_menus.xml"
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
    "images": ["static/description/background.png", ],
    "price": "115",
    "currency": "EUR"
}
