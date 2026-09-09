# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

DEFAULT_PARAMS = {
    'app_system_name': 'DeepOS',
    'app_show_documentation': 'True',
    'app_show_support': 'True',
    'app_show_account': 'True',
    'app_show_poweredby': 'False',
    'app_poweredby_text': 'DeepOS',
    'app_poweredby_url': 'https://www.deeposapps.com',
    'app_documentation_url': 'https://www.deeposapps.com',
    'app_support_url': 'https://www.deeposapps.com',
    'app_account_title': 'DeepOS',
    'app_account_url': 'https://www.deeposapps.com',
    'app_enterprise_url': 'https://www.deeposapps.com',
    'app_ribbon_name': '',
    'app_ribbon_color': '#f0f0f0',
    'app_ribbon_background_color': 'rgba(255,0,0,.4)',
}


def _restore_defaults(env):
    config = env['ir.config_parameter'].sudo()
    for key, value in DEFAULT_PARAMS.items():
        config.set_param(key, value)
    env.cr.commit()
    _logger.info('deep_debranding: default debranding parameters restored')


def uninstall_hook(env):
    """Restaure les valeurs par défaut à la désinstallation."""
    _restore_defaults(env)


def post_init_hook(env):
    """Crée la vue du copyright frontend si le module website est installé."""
    website_installed = env['ir.module.module'].sudo().search_count([
        ('name', '=', 'website'),
        ('state', '=', 'installed'),
    ])
    if not website_installed:
        return
    if env['ir.ui.view'].sudo().search_count([('name', '=', 'deep_debranding.copyright_name')]):
        return
    try:
        view = env['ir.ui.view'].sudo().create({
            'name': 'deep_debranding.copyright_name',
            'type': 'qweb',
            'inherit_id': env.ref('web.frontend_layout').id,
            'key': 'deep_debranding.copyright_name',
            'mode': 'extension',
            'arch': """
                <xpath expr="//span[hasclass('o_footer_copyright_name')]" position="replace">
                    <span class="o_footer_copyright_name me-2" t-if="request and request.env['ir.config_parameter'].sudo().get_param('app_copyright_text')">
                        <t t-esc="request.env['ir.config_parameter'].sudo().get_param('app_copyright_text')"/>
                    </span>
                    <span class="o_footer_copyright_name me-2" t-else="">Copyright &amp;copy;
                        <span t-field="res_company.name" itemprop="name"/>
                    </span>
                </xpath>
            """,
        })
        env.cr.commit()
        _logger.info('deep_debranding: frontend copyright view created (%s)', view.id)
    except Exception as e:
        _logger.warning('deep_debranding: could not create copyright view: %s', e)
        env.cr.rollback()
