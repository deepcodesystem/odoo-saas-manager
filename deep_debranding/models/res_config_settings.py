# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    app_system_name = fields.Char(
        string='System Name',
        help="Nom affiché à la place de 'Odoo' (titre du web client, page de connexion, édition)",
        default='DeepOS',
        config_parameter='app_system_name',
    )

    app_show_poweredby = fields.Boolean(
        string='Show "Powered by"',
        help="Affiche la mention 'Powered by' en bas de la page de connexion",
        config_parameter='app_show_poweredby',
    )
    app_poweredby_text = fields.Char(
        string='"Powered by" Text',
        config_parameter='app_poweredby_text',
    )
    app_poweredby_url = fields.Char(
        string='"Powered by" URL',
        config_parameter='app_poweredby_url',
    )
    app_copyright_text = fields.Char(
        string='Footer Copyright',
        help="Texte du copyright du footer frontend (nécessite le module website)",
        config_parameter='app_copyright_text',
    )

    app_show_documentation = fields.Boolean(
        string='Show Documentation',
        help="Affiche l'item Documentation dans le menu utilisateur",
        config_parameter='app_show_documentation',
    )
    app_documentation_url = fields.Char(
        string='Documentation URL',
        config_parameter='app_documentation_url',
    )
    app_show_support = fields.Boolean(
        string='Show Support',
        help="Affiche l'item Support dans le menu utilisateur",
        config_parameter='app_show_support',
    )
    app_support_url = fields.Char(
        string='Support URL',
        config_parameter='app_support_url',
    )
    app_show_account = fields.Boolean(
        string='Show My Account',
        help="Affiche l'item 'Mon compte' dans le menu utilisateur",
        config_parameter='app_show_account',
    )
    app_account_title = fields.Char(
        string='Account Item Title',
        config_parameter='app_account_title',
    )
    app_account_url = fields.Char(
        string='Account URL',
        config_parameter='app_account_url',
    )

    app_show_enterprise = fields.Boolean(
        string='Show Enterprise Tag',
        help="Décocher pour masquer les tags Enterprise dans les applications",
        config_parameter='app_show_enterprise',
    )
    app_show_share = fields.Boolean(
        string='Show Share',
        help="Décocher pour masquer les boutons de partage",
        config_parameter='app_show_share',
    )
    app_show_lang = fields.Boolean(
        string='Show Quick Language Switcher',
        help="Affiche le sélecteur rapide de langues dans le menu utilisateur",
        config_parameter='app_show_lang',
    )
    app_show_debug = fields.Boolean(
        string='Show Quick Debug',
        help="Affiche le mode développeur (et le quitte) dans le menu utilisateur — réservé aux gestionnaires",
        config_parameter='app_show_debug',
    )
    module_odoo_referral = fields.Boolean(
        string='Show Odoo Referral',
        help="Décocher pour masquer les recommandations Odoo Referral",
    )

    app_enterprise_url = fields.Char(
        string='Enterprise Modules URL',
        help="Réécrit l'URL du site des modules sous licence Enterprise",
        config_parameter='app_enterprise_url',
    )

    app_ribbon_name = fields.Char(
        string='Environment Ribbon',
        help="Texte du ruban affiché dans le backend (ex. TEST, DÉMO). Vide = masqué",
        config_parameter='app_ribbon_name',
    )
    app_ribbon_color = fields.Char(
        string='Ribbon Color',
        config_parameter='app_ribbon_color',
    )
    app_ribbon_background_color = fields.Char(
        string='Ribbon Background Color',
        config_parameter='app_ribbon_background_color',
    )

    @api.model
    def set_module_url(self):
        """Réécrit l'URL du site des modules Enterprise vers la marque cliente."""
        self.env['ir.module.module'].sudo().search([
            ('license', 'like', 'OEEL'),
            ('website', '!=', False),
        ]).write({
            'website': self.env['ir.config_parameter'].sudo().get_param(
                'app_enterprise_url', 'https://www.deeposapps.com'
            ),
        })
        return True
