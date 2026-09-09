# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'SaaS Manager',
    'version': '18.0.1.29.2',
    'category': 'Administration',
    'summary': 'Multi-DB SaaS management with ultra-fast provisioning',
    'description': '''
        SaaS Manager - Multi-DB Architecture
        ====================================
        
        Manage Odoo SaaS instances with PostgreSQL template cloning.
        
        Features:
        * Multi-DB architecture (1 Odoo, N databases)
        * Template Clone System (10s provisioning)
        * Vertical templates (Restaurant, E-commerce, Services)
        * Subscription plans (Starter, Pro, Enterprise)
        * Automatic suspension on expiry
        * User limits enforcement
        * Monitoring and metrics
        
        Performance:
        * Provisioning: 10s (vs 120s traditional)
        * Capacity: 100+ clients on 64GB server
        * Infrastructure cost: -90% vs containers
    ''',
    'author': 'DeepCode',
    'website': 'https://www.deepcode.ma',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'mail',
        'portal',
    ],
    'external_dependencies': {
        'python': ['psycopg2', 'requests', 'PyJWT'],
    },
    'data': [
        # Security
        'security/saas_security.xml',
        'security/ir.model.access.csv',
        
        # Configuration
        'data/ir_config_parameter.xml',
        'data/mail_activity_type_data.xml',

        # Master data
        'data/saas_server_data.xml',
        'data/saas_template_data.xml',
        'data/saas_instance_stage_data.xml',

        # Automation
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',
        
        # Views
        'views/saas_server_views.xml',
        'views/saas_template_views.xml',
        'views/saas_instance_views.xml',
        #'views/saas_dashboard_views.xml',
        'views/saas_menu.xml',
    ],
    'assets': {
    #   'web.assets_backend': [
    #        'saas_manager/static/src/css/saas_dashboard.css',
    #        'saas_manager/static/src/js/saas_dashboard.js',
    #    ],
        'web.assets_frontend': [
            'saas_manager/static/src/css/saas_portal.css',
            'saas_manager/static/src/js/saas_portal.js',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
