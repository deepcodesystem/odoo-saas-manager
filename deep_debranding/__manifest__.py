# -*- coding: utf-8 -*-
# Part of GetapERP. See LICENSE file for full copyright and licensing details.
{
    'name': 'DeepOS Debranding',
    'version': '18.0.1.0.0',
    'author': 'GetapERP',
    'category': 'SaaS',
    'website': 'https://www.deepcode.ma',
    'license': 'LGPL-3',
    'summary': 'White-label Odoo : nom système, Powered by, user menu, ruban, édition',
    'description': """
Debranding / White-label pour instances SaaS GetapERP
=====================================================
- Nom système (remplace "Odoo" dans le titre du web client, <title> et édition Settings)
- "Powered by" personnalisable sur la page de login
- Copyright du footer frontend personnalisable (si website installé)
- Items du user menu : Documentation / Support / Compte (masqués ou URLs custom)
- "{marque} Edition" dans les réglages
- Ruban d'environnement (nom / couleur / fond)
- Masquage tag Enterprise / Share / Odoo Referral

Tout est piloté par ir.config_parameter via Réglages > Général > Debranding.
Clés de configuration conservées identiques à l'ancien module (préfixe app_*).
Aucun hook destructif : uninstall_hook restaure les valeurs par défaut.
""",
    'depends': ['base', 'web', 'portal'],
    'data': [
        'security/res_groups.xml',
        'data/ir_config_parameter_data.xml',
        'views/web_templates.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'deep_debranding/static/src/scss/ribbon.scss',
            'deep_debranding/static/src/scss/debranding.scss',
            'deep_debranding/static/src/js/webclient.js',
            'deep_debranding/static/src/js/user_menu.js',
            'deep_debranding/static/src/js/ribbon.js',
            'deep_debranding/static/src/js/ui_toggles.js',
            'deep_debranding/static/src/js/res_config_edition.js',
            'deep_debranding/static/src/xml/res_config_edition.xml',
        ],
    },
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
