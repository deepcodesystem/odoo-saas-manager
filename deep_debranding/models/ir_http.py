# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        if not request:
            return result
        param = request.env['ir.config_parameter'].sudo().get_param

        def get_bool(key, default=False):
            val = param(key)
            if val is None:
                return default
            return str(val).lower() in ('1', 'true', 'yes')

        result['deep_system_name'] = param('app_system_name') or 'DeepOS'
        result['deep_show_documentation'] = get_bool('app_show_documentation')
        result['deep_documentation_url'] = param('app_documentation_url') or ''
        result['deep_show_support'] = get_bool('app_show_support')
        result['deep_support_url'] = param('app_support_url') or ''
        result['deep_show_account'] = get_bool('app_show_account')
        result['deep_account_title'] = param('app_account_title') or ''
        result['deep_account_url'] = param('app_account_url') or ''
        result['deep_show_poweredby'] = get_bool('app_show_poweredby')
        result['deep_show_enterprise'] = get_bool('app_show_enterprise')
        result['deep_show_share'] = get_bool('app_show_share')
        result['deep_show_lang'] = get_bool('app_show_lang')
        result['deep_show_debug'] = get_bool('app_show_debug')
        result['deep_user_lang'] = self.env.user.lang
        result['deep_lang_list'] = self.env['res.lang'].search_read([], ['code', 'name'])
        result['deep_is_erp_manager'] = self.env.user.has_group('base.group_erp_manager')
        return result
