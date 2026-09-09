# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'SaaS Agent',
    'version': '18.0.1.1.0',
    'summary': 'Agent de contrôle pour instances SaaS (SSO, quotas)',
    'category': 'Administration',
    'author': 'DeepCode',
    'website': 'https://www.deepcode.ma',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/ir.model.access.csv',
    ],
    'external_dependencies': {
        'python': ['PyJWT'],
    },
    'installable': True,
    'application': False,
}

