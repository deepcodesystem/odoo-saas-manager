# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
SaaS Instance Model
===================
Instance client avec provisioning automatisé.
Client instance with automated provisioning.
"""

import logging
import secrets
import string
import requests
import time
import jwt
from datetime import datetime, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SaaSInstance(models.Model):
    """
    SaaS Instance - Core Provisioning System
    
    Représente une instance client avec provisioning automatisé via
    clonage PostgreSQL des templates.
    
    Represents a client instance with automated provisioning via
    PostgreSQL template cloning.
    """
    _name = 'saas.instance'
    _description = 'SaaS Instance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Instance Name',
        required=True,
        tracking=True,
        help="Name of the instance"
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        tracking=True,
        ondelete='restrict',
        default=lambda self: self.env.user.partner_id,
        help="Customer owning this instance"
    )
    database_name = fields.Char(
        string='Database Name',
        required=True,
        tracking=True,
        help="PostgreSQL database name"
    )
    subdomain = fields.Char(
        string='Subdomain',
        required=True,
        tracking=True,
        help="Subdomain (e.g., 'client1')"
    )
    domain = fields.Char(
        string='Full Domain',
        compute='_compute_domain',
        store=True,
        help="Full domain (e.g., 'client1.example.com')"
    )
    protocol = fields.Selection([
        ('http', 'HTTP'),
        ('https', 'HTTPS'),
    ], string='Protocol', default='https', required=True,
        help="Protocol to use when accessing the instance (HTTP for development, HTTPS for production)")
    template_id = fields.Many2one(
        'saas.template',
        string='Template',
        required=True,
        tracking=True,
        ondelete='restrict',
        help="Template used for this instance"
    )
    server_id = fields.Many2one(
        'saas.server',
        string='Server',
        required=True,
        tracking=True,
        ondelete='restrict',
        domain="[('state', '=', 'active'), ('available_capacity', '>', 0)]",
        default=lambda self: self._get_default_server(),
        help="Server hosting this instance"
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('provisioning', 'Provisioning'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('expired', 'Expired'),
        ('terminated', 'Terminated'),
    ], string='State', default='draft', required=True, tracking=True)
    stage_id = fields.Many2one(
        'saas.instance.stage',
        string='Stage',
        tracking=True,
        ondelete='restrict',
        # default intentionally not set to avoid queries during module init
        group_expand='_read_group_stage_ids',
        domain=[('active', '=', True)],
        index=True,
    )

    admin_login = fields.Char(
        string='Admin Login',
        tracking=True,
        help="Administrator login"
    )
    admin_password = fields.Char(
        string='Admin Password',
        groups='saas_manager.group_saas_admin',
        copy=False,
        help="Administrator password (restricted to SaaS Administrators)"
    )
    agent_secret = fields.Char(
        string='Agent Secret',
        groups='saas_manager.group_saas_admin',
        copy=False,
        help="Shared secret with saas_agent for JWT signatures"
    )
    agent_impersonate_login = fields.Char(
        string='SSO Login',
        help="Login utilisé pour l'impersonation par défaut"
    )
    company_name = fields.Char(
        string='Company Name',
        help="Nom de la société cliente à appliquer sur l'instance. "
             "Vide : utilise le partner commercial (société) du client, "
             "à défaut le nom du partner.",
    )

    # User Limit Management
    user_limit = fields.Integer(
        string='User Limit',
        #compute='_compute_user_limit',
        store=True,
        readonly=False,
        tracking=True,
        help="Maximum number of users allowed (from plan)"
    )
    current_users = fields.Integer(
        string='Current Users',
        compute='_compute_current_users',
        store=False,
        help="Current number of active users in instance (last synced value)"
    )
    last_users_count = fields.Integer(
        string='Last Users Count',
        default=0,
        help="Last user count synced from the instance (avoids RPC on every read)"
    )
    users_percentage = fields.Float(
        string='Users Usage %',
        compute='_compute_users_percentage',
        store=False,
        help="Percentage of user limit used"
    )
    last_sync_date = fields.Datetime(
        string='Last User Sync',
        readonly=True,
        help="Last time user limit was synced to instance"
    )
    storage_used = fields.Float(
        string='Storage Used (GB)',
        default=0.0,
        help="Database size in GB (updated by the monitoring cron)",
    )
    monitor_failures = fields.Integer(
        string='Monitoring Failures',
        default=0,
        help="Consecutive health check failures (reset on success)"
    )
    activation_date = fields.Datetime(
        string='Activation Date',
        tracking=True,
        help="Date when instance was activated"
    )
    expiration_date = fields.Datetime(
        string='Expiration Date',
        tracking=True,
        help="Date when instance will expire"
    )
    version = fields.Char(
        string='Odoo Version',
        default='18.0',
        help="Odoo version"
    )
    notes = fields.Text(
        string='Notes',
        help="Internal notes"
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    color = fields.Integer(
        string='Color Index',
        help="Color for kanban view"
    )

    _sql_constraints = [
        ('database_name_unique', 'UNIQUE(database_name)', 'Database name must be unique!'),
        ('subdomain_unique', 'UNIQUE(subdomain)', 'Subdomain must be unique!'),
    ]

    @api.depends('subdomain')
    def _compute_domain(self):
        """
        Calcule le domaine complet depuis le sous-domaine.
        Compute full domain from subdomain.
        """
        base_domain = self.env['ir.config_parameter'].sudo().get_param(
            'saas.base_domain', 'example.com'
        )
        for instance in self:
            if instance.subdomain:
                instance.domain = f"{instance.subdomain}.{base_domain}"
            else:
                instance.domain = False

    def _get_default_server(self):
        """
        Obtenir le serveur par défaut avec le plus de capacité disponible.
        Get default server with most available capacity.
        """
        Server = self.env['saas.server']
        try:
            return Server.get_available_server(min_capacity_percent=10)
        except UserError:
            # If no server with 10% capacity, try to get any active server
            return Server.search([('state', '=', 'active')], limit=1)

    @api.model
    def _stage_for_state(self, state):
        Stage = self.env['saas.instance.stage']
        try:
            if hasattr(Stage, '_table_exists') and not Stage._table_exists():
                return Stage.browse()
            return Stage.search([('state', '=', state)], order='sequence, id', limit=1)
        except Exception:
            return Stage.browse()

    @api.model
    def _default_stage_id(self):
        Stage = self.env['saas.instance.stage']
        try:
            if hasattr(Stage, '_table_exists') and not Stage._table_exists():
                return False
            stage = self._stage_for_state('draft')
            if not stage:
                stage = Stage.search([], order='sequence, id', limit=1)
            return stage.id
        except Exception:
            return False

    @api.model
    def _read_group_stage_ids(self, stages, domain, order=None):
        order = order or 'sequence, id'
        return stages.search([], order=order)

    #@api.depends('plan_id', 'plan_id.user_limit')
    #def _compute_user_limit(self):
    #    """Get user limit from plan"""
    #    for instance in self:
    #        if instance.plan_id and hasattr(instance.plan_id, 'user_limit'):
    #            instance.user_limit = instance.plan_id.user_limit
    #        else:
    #            instance.user_limit = 10  # Default limit

    def _compute_current_users(self):
        """
        Return the last synced user count (no RPC — avoids N+1 network calls
        when listing instances). Use action_refresh_users_count or the sync
        cron to fetch fresh values from the instance.
        """
        for instance in self:
            if instance.state in ('active', 'suspended'):
                instance.current_users = instance.last_users_count
            else:
                instance.current_users = 0

    def _get_database_size_gb(self):
        """Taille de la base de l'instance en Go (pg_database_size).

        Connexion à la base 'postgres' du serveur hébergeant l'instance.
        Retourne 0.0 en cas d'échec.
        """
        self.ensure_one()
        import psycopg2

        server = self.server_id
        try:
            conn = psycopg2.connect(
                host=server.db_host or 'localhost',
                port=server.db_port or 5432,
                user=server.db_user or 'odoo',
                password=server.db_password or '',
                dbname='postgres',
                connect_timeout=10,
            )
            try:
                with conn.cursor() as cr:
                    cr.execute("SELECT pg_database_size(%s)", [self.database_name])
                    row = cr.fetchone()
                    if row and row[0]:
                        return round(row[0] / (1024 ** 3), 3)
            finally:
                conn.close()
        except Exception as exc:
            _logger.warning("Could not get database size for %s: %s", self.database_name, exc)
        return 0.0

    def _ping_instance(self):
        """Vérifier la disponibilité de l'instance via /web/health.

        Retourne True si le endpoint répond HTTP 200.
        """
        self.ensure_one()
        base_url = self._build_instance_url()
        if not base_url:
            return False
        try:
            response = requests.get(
                f"{base_url}/web/health",
                timeout=10,
                verify=self._ssl_verify,
                allow_redirects=True,
            )
            return response.status_code == 200
        except requests.exceptions.RequestException as exc:
            _logger.debug("Health check failed for %s: %s", self.name, exc)
            return False

    @api.model
    def cron_monitor_instances(self):
        """
        CRON: Monitorer les instances actives (santé HTTP + taille base).

        - storage_used ← pg_database_size
        - /web/health : 2 échecs consécutifs → message chatter + activity
          (jamais de suspension automatique)
        """
        _logger.info("Running instance monitoring...")

        admin_users = self._get_saas_admin_users()
        activity_type = 'saas_manager.mail_act_saas_alert'
        max_failures = 2

        active_instances = self.search([('state', '=', 'active')])
        for instance in active_instances:
            try:
                # Storage
                instance.storage_used = instance._get_database_size_gb()

                # Health
                if instance._ping_instance():
                    if instance.monitor_failures:
                        instance.write({'monitor_failures': 0})
                    continue

                failures = instance.monitor_failures + 1
                instance.write({'monitor_failures': failures})

                if failures >= max_failures:
                    body = _(
                        "Instance unreachable %(failures)d consecutive times "
                        "(health check on %(url)s failed).",
                        failures=failures,
                        url=instance._build_instance_url() or 'N/A',
                    )
                    instance.message_post(body=body, message_type='comment')
                    for user in admin_users:
                        try:
                            instance.activity_schedule(
                                activity_type,
                                user_id=user.id,
                                note=body,
                            )
                        except Exception as act_exc:
                            _logger.warning(
                                "Could not schedule alert activity on %s: %s",
                                instance.name, act_exc,
                            )
                    _logger.warning("Instance %s unreachable (failures=%d)",
                                    instance.name, failures)

            except Exception as e:
                _logger.error(f"Monitoring failed for {instance.name}: {str(e)}")

        _logger.info("Instance monitoring done: %d instances checked", len(active_instances))

    def _get_saas_admin_users(self):
        """Utilisateurs actifs du groupe SaaS Administrator (pour les alertes)."""
        return self.env.ref('saas_manager.group_saas_admin').sudo().users.filtered('active')

    @api.depends('current_users', 'user_limit')
    def _compute_users_percentage(self):
        """Calculate usage percentage"""
        for instance in self:
            if instance.user_limit > 0:
                instance.users_percentage = (instance.current_users / instance.user_limit) * 100
            else:
                instance.users_percentage = 0.0

    @api.model
    def _generate_random_password(self, length=16):
        """Génère un mot de passe garantissant la politique de complexité Odoo.

        Garantit au minimum : 1 majuscule, 1 minuscule, 1 chiffre, 1 caractère spécial.
        """
        upper = string.ascii_uppercase
        lower = string.ascii_lowercase
        digits = string.digits
        special = "!@#$%^&*"
        all_chars = upper + lower + digits + special

        # Garantir au moins un caractère de chaque catégorie
        mandatory = [
            secrets.choice(upper),
            secrets.choice(lower),
            secrets.choice(digits),
            secrets.choice(special),
        ]
        rest = [secrets.choice(all_chars) for _ in range(max(length - 4, 4))]
        pool = mandatory + rest
        secrets.SystemRandom().shuffle(pool)
        return ''.join(pool)

    @api.constrains('subdomain')
    def _check_subdomain(self):
        """
        Valider le format du sous-domaine.
        Validate subdomain format.
        """
        for instance in self:
            if instance.subdomain:
                # Only lowercase alphanumeric and hyphens
                if not all(c.isalnum() or c == '-' for c in instance.subdomain):
                    raise ValidationError(_(
                        'Subdomain can only contain lowercase letters, numbers, and hyphens.'
                    ))
                if not instance.subdomain[0].isalnum() or not instance.subdomain[-1].isalnum():
                    raise ValidationError(_(
                        'Subdomain must start and end with a letter or number.'
                    ))

    @api.constrains('subdomain', 'database_name')
    def _check_subdomain_matches_database(self):
        """Avertissement (non bloquant) si subdomain != database_name.

        Le routing SaaS repose sur dbfilter = ^%d$ : le sous-domaine doit
        correspondre au nom de la base.
        """
        for instance in self:
            if (
                instance.database_name
                and instance.subdomain
                and instance.subdomain != instance.database_name
            ):
                _logger.warning(
                    "Instance %s: subdomain '%s' does not match database name "
                    "'%s' (dbfilter routing requires them to be equal)",
                    instance.name, instance.subdomain, instance.database_name,
                )
                if instance.id:
                    instance.message_post(
                        body=_(
                            "Warning: subdomain '%(subdomain)s' does not match "
                            "the database name '%(database)s'. With dbfilter "
                            "routing, they must be identical.",
                            subdomain=instance.subdomain,
                            database=instance.database_name,
                        ),
                    )

    def action_provision_instance(self):
        """
        Provisionner l'instance complète (orchestration).
        Provision the complete instance (orchestration).
        
        Workflow:
        1. Valider les prérequis
        2. Cloner la base de données template
        3. Neutraliser les données sensibles
        4. Personnaliser l'instance
        5. Créer l'administrateur client
        6. Configurer le sous-domaine
        7. Activer l'instance
        """
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_('Only draft instances can be provisioned.'))
        
        if not self.template_id.is_template_ready:
            raise UserError(_('Template %s is not ready for cloning.') % self.template_id.name)
        
        # Validate server state
        if self.server_id.state != 'active':
            raise UserError(
                _("Cannot provision instance on server '%s'.\n\n"
                  "Server state is '%s'. Server must be 'active' to provision instances.\n\n"
                  "Please activate the server or select a different server.") % (self.server_id.name, self.server_id.state)
            )
        
        # Validate server capacity
        if self.server_id.available_capacity < 10:
            raise UserError(
                _("Cannot provision instance on server '%s'.\n\n"
                  "Server has only %.1f%% capacity available. Minimum 10%% required.\n\n"
                  "Please select a different server or increase max instances on this server.") % (self.server_id.name, self.server_id.available_capacity)
            )
        
        try:
            # Update state to provisioning
            # (le commit explicite est volontairement évité : l'atomicité de la
            # transaction est préservée et l'état 'draft' est restauré en cas d'échec)
            self.write({'state': 'provisioning'})
            
            _logger.info(f"Starting provisioning for instance: {self.name}")
            
            # Step 1: Clone template database (~5s)
            self._clone_template_database()
            
            # Step 2: Neutralize sensitive data (~2s)
            self._neutralize_database()
            
            # Step 3: Customize instance (~2s)
            self._customize_instance()
            
            # Step 4: Create client admin (~1s)
            self._create_client_admin()

            # Step 4bis: Push agent secret for JWT (best effort)
            self._ensure_agent_secret()
            self._push_agent_secret_to_instance()

            # Step 4ter: Install l10n module based on country (best effort)
            self._install_l10n_module()

            # Step 5: Configure subdomain (~1s)
            self._configure_subdomain()
            
            # Step 6: Activate instance
            self.write({
                'state': 'active',
                'activation_date': fields.Datetime.now(),
            })
            
            _logger.info(f"Instance {self.name} provisioned successfully")

            # Step 7: Sync user limit to instance
            if self.user_limit:
                if self._send_user_limit_to_instance():
                    self.write({'last_sync_date': fields.Datetime.now()})

            # Step 7bis: Sync expiration date to instance
            if self.expiration_date:
                self._send_expiration_to_instance(False, self.expiration_date)

            # Step 8: Send provisioning email to customer
            self._send_instance_email('provisioned')

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Instance Provisioned'),
                    'message': _('Instance %s is now active at %s') % (self.name, self.domain),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Provisioning failed for {self.name}: {str(e)}")
            self.write({'state': 'draft'})
            raise UserError(_('Provisioning failed: %s') % str(e))

    def _clone_template_database(self):
        """
        Cloner la base de données template PostgreSQL.
        Clone the PostgreSQL template database.
        
        TODO Phase 2: Implement with psycopg2
        
        Example implementation:
            import psycopg2
            
            # Connect to PostgreSQL
            conn = psycopg2.connect(
                dbname='postgres',
                user=config.get('db_user'),
                password=config.get('db_password'),
                host=config.get('db_host'),
                port=config.get('db_port')
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            # Clone template
            template_db = self.template_id.template_db
            target_db = self.database_name
            
            cursor.execute(f"CREATE DATABASE {target_db} WITH TEMPLATE {template_db}")
            cursor.close()
            conn.close()
            
            _logger.info(f"Database {target_db} cloned from {template_db}")
        """
        # Validate that template and instance are on the same server
        if self.template_id.server_id != self.server_id:
            raise UserError(
                _("Template and instance must be on the same server.\n\n"
                  "Template '%s' is on server '%s'\n"
                  "Instance '%s' is on server '%s'\n\n"
                  "Please select a template on the same server or change the instance server.") % (
                      self.template_id.name, self.template_id.server_id.name,
                      self.name, self.server_id.name
                  )
            )
        
        _logger.info(f"Cloning template {self.template_id.template_db} to {self.database_name} on server {self.server_id.name}")
        
        # Call template's clone method which uses server's DB configuration
        self.template_id.clone_template_db(self.database_name)

    # Purge légère du template : données métier de démonstration à supprimer
    # dans chaque instance clonée. Ordre respectant les clés étrangères.
    # Chaque requête est gardée par to_regclass (module non installé → ignorée).
    NEUTRALIZE_LIGHT_QUERIES = [
        # Communication (mails en attente, tracking, messages de chatter)
        ("mail_mail", "DELETE FROM mail_mail"),
        ("mail_tracking_value", "DELETE FROM mail_tracking_value"),
        ("mail_activity", "DELETE FROM mail_activity"),
        ("mail_message", "DELETE FROM mail_message"),
        # Comptabilité
        ("account_partial_reconcile", "DELETE FROM account_partial_reconcile"),
        ("account_move_line", "DELETE FROM account_move_line"),
        ("account_move", "DELETE FROM account_move"),
        # Ventes / Achats
        ("sale_order_line", "DELETE FROM sale_order_line"),
        ("sale_order", "DELETE FROM sale_order"),
        ("purchase_order_line", "DELETE FROM purchase_order_line"),
        ("purchase_order", "DELETE FROM purchase_order"),
        # Stock
        ("stock_move_line", "DELETE FROM stock_move_line"),
        ("stock_move", "DELETE FROM stock_move"),
        ("stock_picking", "DELETE FROM stock_picking"),
        # Secrets / état SaaS hérités du template (CRITIQUE : sans purge,
        # toutes les instances partageraient le saas_agent.secret du template)
        ("ir_config_parameter", """
            DELETE FROM ir_config_parameter
             WHERE key IN (
                'saas_agent.secret',
                'saas_agent.user_limit',
                'saas_agent.expiration_date',
                'saas_agent.suspended',
                'saas_agent.instance_uuid',
                'saas_agent.impersonate_user_id'
             )
        """),
        # Utilisateurs de démo : hors système (1) et admin (2), et hors
        # utilisateurs référencés par un ir.model.data (préserve base.public_user,
        # base.default_user, base.template_portal… requis par Odoo)
        ("res_users", """
            DELETE FROM res_users
             WHERE id NOT IN (1, 2)
               AND NOT EXISTS (SELECT 1 FROM ir_model_data d
                                WHERE d.model = 'res.users' AND d.res_id = res_users.id)
        """),
        # Partenaires hors sociétés, hors partenaires des utilisateurs restants,
        # et hors partenaires référencés par un ir.model.data
        ("res_partner", """
            DELETE FROM res_partner
             WHERE NOT EXISTS (SELECT 1 FROM res_company c WHERE c.partner_id = res_partner.id)
               AND NOT EXISTS (SELECT 1 FROM res_users u WHERE u.partner_id = res_partner.id)
               AND NOT EXISTS (SELECT 1 FROM ir_model_data d
                                WHERE d.model = 'res.partner' AND d.res_id = res_partner.id)
        """),
    ]

    def _get_neutralize_scope(self):
        """Scope de purge : 'none' (rien), 'light' (purge métier, défaut)."""
        return self.env['ir.config_parameter'].sudo().get_param(
            'saas.neutralize_scope', 'light'
        )

    def _purge_database_light(self):
        """Exécute la purge light sur la base de l'instance via psycopg2.

        Fonctionne en local comme sur un serveur distant (les credentials
        PostgreSQL du serveur sont utilisés).
        """
        self.ensure_one()
        import psycopg2

        server = self.server_id
        conn = psycopg2.connect(
            host=server.db_host or 'localhost',
            port=server.db_port or 5432,
            user=server.db_user or 'odoo',
            password=server.db_password or '',
            dbname=self.database_name,
            connect_timeout=30,
        )
        try:
            with conn.cursor() as cr:
                total = 0
                for table, query in self.NEUTRALIZE_LIGHT_QUERIES:
                    cr.execute("SELECT to_regclass(%s)", [table])
                    if not cr.fetchone()[0]:
                        continue
                    cr.execute(query)
                    total += cr.rowcount
                    _logger.info("Neutralize %s on %s: %s rows", table, self.database_name, cr.rowcount)
            conn.commit()
            _logger.info("Light neutralization of %s done: %s rows purged", self.database_name, total)
        finally:
            conn.close()

    def _neutralize_database(self):
        """
        Purger les données sensibles / de démonstration de l'instance clonée.

        Scope piloté par le paramètre `saas.neutralize_scope` :
        - 'none'  : aucune purge (déconseillé en production)
        - 'light' : purge métier ciblée (défaut)

        La neutralisation native Odoo (mails/crons) est recommandée en amont
        sur les templates via scripts/neutralize_template.py.
        """
        scope = self._get_neutralize_scope()
        if scope == 'none':
            _logger.info("Neutralization skipped for %s (scope=none)", self.name)
            return
        if scope != 'light':
            _logger.warning("Unknown saas.neutralize_scope %r, falling back to light", scope)

        _logger.info("Neutralizing database %s (scope=light)", self.database_name)
        try:
            self._purge_database_light()
            self.message_post(
                body=_("Instance neutralized: template demo data purged."),
            )
        except Exception as exc:
            # Non-bloquant : log + chatter, le provisioning continue
            _logger.error("Neutralization failed for %s: %s", self.database_name, exc)
            self.message_post(
                body=_("Neutralization warning: purge failed (%s). "
                       "The instance may still contain template demo data.") % exc,
            )

    def _customize_instance(self):
        """
        Personnaliser l'instance clonée avec les informations du client.

        Appliqué sur la société principale (res.company id 1) :
        - name, email, vat, phone, mobile, website depuis le partner client
        - adresse complète : street, street2, zip, city, country (par code ISO)
        - logo depuis l'image du partner client (si présente)

        Local : Registry direct. Distant : RPC avec les credentials admin
        (l'appel se fait avant la création de l'admin client → on utilise
        les credentials du template).
        """
        self.ensure_one()

        partner = self.partner_id
        if not partner:
            _logger.info("No partner on instance %s, skipping customization", self.name)
            return

        # Source des informations société : le partner commercial (la société
        # pour un contact rattaché), sinon le partner lui-même. Le champ
        # company_name de l'instance est prioritaire sur le nom.
        source = partner.commercial_partner_id or partner
        _logger.info(
            "Customizing %s from partner %s (commercial=%s, is_company=%s)",
            self.database_name, partner.name, source.name, source.is_company,
        )

        company_vals = {
            'name': self.company_name or source.name or False,
            'email': source.email or False,
            'vat': source.vat or False,
            'phone': source.phone or False,
            'mobile': source.mobile or False,
            'website': source.website or False,
            'street': source.street or False,
            'street2': source.street2 or False,
            'zip': source.zip or False,
            'city': source.city or False,
        }
        company_vals = {k: v for k, v in company_vals.items() if v}
        logo_data = source.image_1920 or False
        # Le pays est résolu par code ISO côté instance (les ids peuvent différer)
        country_code = source.country_id.code if source.country_id else False

        _logger.info("Customizing instance %s with values: %s%s",
                     self.database_name, list(company_vals),
                     f" + country={country_code}" if country_code else "")

        try:
            if self._is_local_server():
                self._customize_instance_local(company_vals, logo_data, country_code)
            else:
                self._customize_instance_rpc(company_vals, logo_data, country_code)
        except Exception as exc:
            # Non-bloquant : la personnalisation reste manuelle si elle échoue
            _logger.error("Customization failed for %s: %s", self.database_name, exc)

    def _customize_instance_local(self, company_vals, logo_data, country_code):
        from odoo import api as _api, SUPERUSER_ID
        from odoo.modules.registry import Registry as _Registry
        registry = _Registry(self.database_name)
        with registry.cursor() as cr:
            env = _api.Environment(cr, SUPERUSER_ID, {})
            company = env['res.company'].browse(1)
            vals = dict(company_vals)
            if logo_data:
                vals['logo'] = logo_data
            if country_code:
                country = env['res.country'].search(
                    [('code', '=', country_code)], limit=1)
                if country:
                    vals['country_id'] = country.id
            company.write(vals)
        _logger.info("Instance %s customized locally (company=%s)",
                     self.database_name, company_vals.get('name'))

    def _customize_instance_rpc(self, company_vals, logo_data, country_code):
        """Personnalisation via RPC — nécessite des credentials admin.

        À ce stade du provisioning, l'admin client n'existe pas encore :
        on utilise les credentials admin du template si disponibles.
        """
        template = self.template_id
        login = template.template_admin_login
        password = template.template_admin_password
        if not (login and password):
            _logger.warning(
                "No template admin credentials for %s — customization skipped "
                "(set template_admin_login/template_admin_password on the template)",
                self.database_name,
            )
            return

        base = self.server_id.server_url.rstrip('/')
        rpc_url = f"{base}/jsonrpc"

        auth_resp = requests.post(rpc_url, json={
            'jsonrpc': '2.0', 'method': 'call', 'id': 1,
            'params': {
                'service': 'common', 'method': 'authenticate',
                'args': [self.database_name, login, password, {}],
            },
        }, timeout=30, verify=self._ssl_verify)
        uid = auth_resp.json().get('result')
        if not uid:
            _logger.warning("Auth failed for customization on %s", self.database_name)
            return

        vals = dict(company_vals)
        if logo_data:
            vals['logo'] = logo_data
        if country_code:
            # Résoudre le pays par code ISO via RPC
            country_resp = requests.post(rpc_url, json={
                'jsonrpc': '2.0', 'method': 'call', 'id': 2,
                'params': {
                    'service': 'object', 'method': 'execute_kw',
                    'args': [
                        self.database_name, uid, password,
                        'res.country', 'search_read',
                        [[('code', '=', country_code)]], ['id'],
                    ],
                },
            }, timeout=30, verify=self._ssl_verify)
            countries = country_resp.json().get('result', [])
            if countries:
                vals['country_id'] = countries[0]['id']
            else:
                _logger.warning(
                    "Country %s not found on instance %s", country_code, self.database_name
                )

        requests.post(rpc_url, json={
            'jsonrpc': '2.0', 'method': 'call', 'id': 3,
            'params': {
                'service': 'object', 'method': 'execute_kw',
                'args': [
                    self.database_name, uid, password,
                    'res.company', 'write', [[1], vals],
                ],
            },
        }, timeout=60, verify=self._ssl_verify)
        _logger.info("Instance %s customized via RPC (company=%s)",
                     self.database_name, company_vals.get('name'))

    def _install_l10n_module(self):
        """Installe le module l10n correspondant au pays saas_country_id via RPC.

        Mapping country.code → l10n module name. Non-bloquant : les erreurs
        sont loggées mais ne font pas échouer le provisioning.
        """
        self.ensure_one()

        L10N_MAP = {
            'MA': 'l10n_ma',
            'SN': 'l10n_sn',
            'FR': 'l10n_fr',
            'BE': 'l10n_be',
            'DZ': 'l10n_dz',
            'TN': 'l10n_tn',
            'CI': 'l10n_ci',
            'CM': 'l10n_cm',
            'DE': 'l10n_de',
            'ES': 'l10n_es',
            'GB': 'l10n_uk',
            'US': 'l10n_us',
            'SA': 'l10n_sa',
            'AE': 'l10n_ae',
        }

        country = getattr(self, 'saas_country_id', None) or self.partner_id.country_id
        if not country:
            _logger.info(
                "No country on instance %s (saas_country_id and partner), skipping l10n install",
                self.name,
            )
            return

        country_code = country.code
        l10n_module = L10N_MAP.get(country_code)
        if not l10n_module:
            _logger.info("No l10n module mapped for country %s on instance %s", country_code, self.name)
            return

        if not self.admin_login or not self.admin_password:
            _logger.warning("No admin credentials to install l10n for %s", self.name)
            return

        server = self.server_id
        base_url = server.server_url.rstrip('/')
        rpc_url = f"{base_url}/jsonrpc"

        def rpc_execute(model, method, args, kwargs=None, timeout=120, call_id=1):
            """Helper RPC execute_kw vers l'instance."""
            return requests.post(rpc_url, json={
                'jsonrpc': '2.0', 'method': 'call', 'id': call_id,
                'params': {
                    'service': 'object', 'method': 'execute_kw',
                    'args': [self.database_name, uid, self.admin_password,
                             model, method, args, kwargs or {}],
                },
            }, timeout=timeout, verify=self._ssl_verify)

        def install_module(module_name):
            """Installer un module sur l'instance (non-bloquant)."""
            search_resp = rpc_execute(
                'ir.module.module', 'search',
                [[['name', '=', module_name]]], timeout=30,
            )
            module_ids = search_resp.json().get('result', [])
            if not module_ids:
                _logger.warning("Module %s not found in instance %s", module_name, self.name)
                return False

            read_resp = rpc_execute(
                'ir.module.module', 'read', [module_ids, ['state']], timeout=30,
            )
            module_info = read_resp.json().get('result', [])
            if module_info and module_info[0].get('state') == 'installed':
                _logger.info("Module %s already installed on %s", module_name, self.name)
                return True

            try:
                install_resp = rpc_execute(
                    'ir.module.module', 'button_immediate_install',
                    [module_ids], timeout=120,
                )
                result = install_resp.json()
                if result.get('error'):
                    _logger.warning(
                        "L10n install RPC error for %s (%s): %s",
                        self.name, module_name,
                        result['error'].get('data', {}).get('message', result['error'])
                    )
                    return False
                _logger.info("L10n module %s install triggered on %s", module_name, self.name)
                return True
            except requests.exceptions.Timeout:
                # button_immediate_install peut provoquer un restart du worker — normal
                _logger.info(
                    "L10n install timed out for %s (expected if worker restarts): module=%s",
                    self.name, module_name
                )
                return True

        try:
            # 1. Authenticate
            auth_resp = requests.post(rpc_url, json={
                'jsonrpc': '2.0', 'method': 'call', 'id': 1,
                'params': {
                    'service': 'common', 'method': 'authenticate',
                    'args': [self.database_name, self.admin_login, self.admin_password, {}],
                },
            }, timeout=30, verify=self._ssl_verify)
            uid = auth_resp.json().get('result')
            if not uid:
                _logger.warning("Auth failed for l10n install on %s", self.name)
                return

            # 2. Installer le module de localisation principal
            # (uniquement le module général — pas les modules additionnels
            # l10n_xx_* qui tireraient des applications hors du modèle métier)
            install_module(l10n_module)

            # 3. Apply chart template via direct registry access (SUPERUSER — contourne les ACL)
            import time as _time
            from odoo import api as _odoo_api, SUPERUSER_ID
            from odoo.modules.registry import Registry as _Registry
            _time.sleep(2)
            try:
                # Registry.new() force un chargement frais : l10n_ma vient
                # d'être installé par un autre worker (RPC) et le registry
                # en cache de CE worker peut ne pas contenir le register des
                # templates du nouveau module (KeyError 'template_data').
                _registry = _Registry.new(self.database_name)
                with _registry.cursor() as _cr:
                    _env = _odoo_api.Environment(_cr, SUPERUSER_ID, {})
                    _company = _env['res.company'].browse(1)
                    _chart_model = _env['account.chart.template']
                    _country = _env['res.country'].search(
                        [('code', '=', country_code)], limit=1
                    )
                    if not _country:
                        _logger.warning(
                            "Country %s not found on %s", country_code, self.name
                        )
                    else:
                        # Odoo 18 : sélection du template par pays
                        _template_code = _chart_model._guess_chart_template(_country)
                        if not _template_code or _template_code == 'generic_coa':
                            _logger.warning(
                                "No chart template for country %s on %s",
                                country_code, self.name,
                            )
                        else:
                            _chart_model.try_loading(
                                _template_code, company=_company, install_demo=False,
                            )
                            # Forcer pays + devise de la société fiscale :
                            # try_loading ne les change que si absents, or le
                            # clone hérite de la config du template (USD/US).
                            # La devise du pays peut être inactive sur le clone
                            # → l'activer avant de l'assigner.
                            _fiscal_currency = _country.currency_id
                            _vals = {'country_id': _country.id}
                            if _fiscal_currency:
                                if not _fiscal_currency.active:
                                    _fiscal_currency.sudo().write({'active': True})
                                    _logger.info(
                                        "Currency %s activated on %s",
                                        _fiscal_currency.name, self.name,
                                    )
                                _vals['currency_id'] = _fiscal_currency.id
                            _company.write(_vals)
                            _logger.info(
                                "Chart template %s applied to main company on %s "
                                "(country=%s, currency=%s)",
                                _template_code, self.name,
                                _country.code, _fiscal_currency.name if _fiscal_currency else 'N/A',
                            )
            except Exception as _ct_exc:
                _logger.warning(
                    "Failed to apply chart template for country %s on %s: %s",
                    country_code, self.name, _ct_exc
                )

        except requests.exceptions.Timeout:
            _logger.info(
                "L10n install timed out for %s (expected if worker restarts): module=%s",
                self.name, l10n_module
            )
        except Exception as exc:
            _logger.warning("Failed to install l10n module %s on %s: %s", l10n_module, self.name, exc)

    def _is_local_server(self):
        """Retourne True si l'instance est hébergée sur ce même serveur Odoo.

        1. Comparaison d'URL (comportement historique)
        2. Fallback : la base est-elle joignable via la config PostgreSQL
           du serveur ? (gère les cas dev.africasys.ma vs deeposapps.africasys.ma
           qui pointent vers le même hôte)
        """
        from urllib.parse import urlparse
        current_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        server_url = self.server_id.server_url or ''
        if (
            urlparse(server_url.rstrip('/')).netloc
            == urlparse(current_url.rstrip('/')).netloc
        ):
            return True

        # Fallback : test de connexion PostgreSQL locale à la base de l'instance
        import psycopg2
        server = self.server_id
        try:
            conn = psycopg2.connect(
                host=server.db_host or 'localhost',
                port=server.db_port or 5432,
                user=server.db_user or 'odoo',
                password=server.db_password or '',
                dbname=self.database_name,
                connect_timeout=5,
            )
            conn.close()
            return True
        except Exception:
            return False

    def _update_admin_via_registry(self, admin_login, admin_password):
        """Mise à jour directe via Registry (serveur local uniquement)."""
        from odoo import api as _api, SUPERUSER_ID
        from odoo.modules.registry import Registry as _Registry
        registry = _Registry(self.database_name)
        with registry.cursor() as cr:
            env = _api.Environment(cr, SUPERUSER_ID, {})
            env['res.users'].browse(2).write({
                'name': self.partner_id.name,
                'login': admin_login,
                'password': admin_password,
                'email': self.partner_id.email or admin_login,
            })
        _logger.info("Admin updated via local registry for %s", self.database_name)

    def _update_admin_via_psql(self, admin_login, admin_password):
        """Mise à jour via psycopg2 direct (serveur distant).

        Utilise passlib pour hasher le mot de passe identiquement à Odoo.
        """
        import psycopg2
        from passlib.context import CryptContext

        server = self.server_id
        crypt_ctx = CryptContext(schemes=['pbkdf2_sha512'], deprecated='auto')
        hashed_password = crypt_ctx.hash(admin_password)
        partner_name = self.partner_id.name
        partner_email = self.partner_id.email or admin_login

        conn = psycopg2.connect(
            host=server.db_host or 'localhost',
            port=server.db_port or 5432,
            user=server.db_user or 'odoo',
            password=server.db_password or '',
            dbname=self.database_name,
            connect_timeout=10,
        )
        try:
            with conn.cursor() as cr:
                cr.execute(
                    "UPDATE res_users SET login=%s, password=%s WHERE id=2",
                    (admin_login, hashed_password),
                )
                cr.execute(
                    """UPDATE res_partner SET name=%s, email=%s
                       WHERE id=(SELECT partner_id FROM res_users WHERE id=2)""",
                    (partner_name, partner_email),
                )
            conn.commit()
            _logger.info("Admin updated via psycopg2 for %s", self.database_name)
        finally:
            conn.close()

    def _create_client_admin(self):
        """
        Créer le compte administrateur client.

        - Serveur local  → Registry + SUPERUSER_ID (indépendant des credentials)
        - Serveur distant → psycopg2 direct sur PostgreSQL distant
        """
        self.ensure_one()

        admin_login = self.admin_login or self.partner_id.email or f"admin@{self.subdomain}"
        admin_password = self.admin_password or self._generate_random_password()

        _logger.info("Creating admin account for instance %s", self.database_name)
        _logger.info("New admin login will be: %s", admin_login)

        try:
            if self._is_local_server():
                self._update_admin_via_registry(admin_login, admin_password)
            else:
                self._update_admin_via_psql(admin_login, admin_password)
        except Exception as e:
            _logger.error(
                "Failed to update admin user for %s: %s",
                self.database_name, e,
            )

        self.write({'admin_login': admin_login, 'admin_password': admin_password})
        _logger.info("Admin credentials stored for instance %s", self.database_name)

    def _configure_subdomain(self):
        """
        Configurer le sous-domaine : cohérence dbfilter + URL de base de l'instance.

        Le routing repose sur `dbfilter = ^%d$` : le sous-domaine est le nom
        de la base et le reverse-proxy gère la résolution wildcard. Cette
        étape aligne donc :
        1. subdomain = database_name
        2. web.base.url de l'instance clonée = https://{database}.{base_domain}
        3. ping post-configuration (non bloquant)
        """
        self.ensure_one()

        # 1. Aligner subdomain sur le nom de base (routing dbfilter)
        if self.subdomain != self.database_name:
            _logger.info(
                "Aligning subdomain '%s' to database name '%s' for %s",
                self.subdomain, self.database_name, self.name,
            )
            self.write({'subdomain': self.database_name})

        instance_url = self._build_instance_url()
        if not instance_url:
            _logger.warning("No domain for %s, skipping base url config", self.name)
            return

        # 2. web.base.url dans l'instance clonée
        try:
            self._set_instance_base_url(instance_url)
        except Exception as exc:
            _logger.warning("Failed to set web.base.url on %s: %s", self.database_name, exc)

        # 3. Ping (non bloquant) : vérifier que le reverse-proxy route
        try:
            response = requests.get(
                f"{instance_url}/web/health",
                timeout=10,
                verify=self._ssl_verify,
            )
            if response.status_code == 200:
                _logger.info("Instance %s reachable at %s", self.name, instance_url)
            else:
                _logger.warning(
                    "Instance %s ping returned HTTP %s — check reverse-proxy "
                    "routing for %s", self.name, response.status_code, instance_url,
                )
        except requests.exceptions.RequestException as exc:
            _logger.warning(
                "Instance %s not reachable at %s yet (%s) — reverse-proxy or "
                "DNS may not be configured", self.name, instance_url, exc,
            )

    def _set_instance_base_url(self, base_url):
        """Écrire web.base.url dans la base de l'instance clonée."""
        self.ensure_one()
        if self._is_local_server():
            from odoo import api as _api, SUPERUSER_ID
            from odoo.modules.registry import Registry as _Registry
            registry = _Registry(self.database_name)
            with registry.cursor() as cr:
                env = _api.Environment(cr, SUPERUSER_ID, {})
                env['ir.config_parameter'].sudo().set_param('web.base.url', base_url)
            _logger.info("web.base.url set locally on %s: %s", self.database_name, base_url)
            return

        # Serveur distant : RPC avec les credentials admin de l'instance
        if not (self.admin_login and self.admin_password):
            _logger.warning(
                "No admin credentials to set web.base.url on %s", self.database_name
            )
            return
        base = self.server_id.server_url.rstrip('/')
        rpc_url = f"{base}/jsonrpc"

        auth_resp = requests.post(rpc_url, json={
            'jsonrpc': '2.0', 'method': 'call', 'id': 1,
            'params': {
                'service': 'common', 'method': 'authenticate',
                'args': [self.database_name, self.admin_login, self.admin_password, {}],
            },
        }, timeout=30, verify=self._ssl_verify)
        uid = auth_resp.json().get('result')
        if not uid:
            _logger.warning("Auth failed to set web.base.url on %s", self.database_name)
            return

        requests.post(rpc_url, json={
            'jsonrpc': '2.0', 'method': 'call', 'id': 2,
            'params': {
                'service': 'object', 'method': 'execute_kw',
                'args': [
                    self.database_name, uid, self.admin_password,
                    'ir.config_parameter', 'set_param',
                    ['web.base.url', base_url],
                ],
            },
        }, timeout=30, verify=self._ssl_verify)
        _logger.info("web.base.url set via RPC on %s: %s", self.database_name, base_url)

    def _send_instance_email(self, event):
        """
        Envoyer l'email de notification lié à un événement d'instance.
        Send instance event notification email to customer.

        Args:
            event (str): suffix of the mail template xml id
                ('provisioned', 'suspended', 'reactivated', 'terminated')

        Uses the 'saas_manager.mail_template_instance_<event>' template.
        Returns True if the email was sent, False otherwise (non-blocking).
        """
        self.ensure_one()
        template_xmlid = f'saas_manager.mail_template_instance_{event}'

        try:
            template = self.env.ref(template_xmlid, raise_if_not_found=False)

            if not template:
                _logger.warning(
                    "Email template '%s' not found. "
                    "Skipping email notification for instance %s",
                    template_xmlid, self.name,
                )
                return False

            if not self.partner_id.email:
                _logger.warning(
                    "Customer %s has no email address. "
                    "Cannot send %s email for instance %s",
                    self.partner_id.name, event, self.name,
                )
                return False

            _logger.info(
                "Sending %s email to %s for instance %s",
                event, self.partner_id.email, self.name,
            )

            template.send_mail(self.id, force_send=True, raise_exception=False)

            _logger.info(
                "%s email sent successfully to %s for instance %s",
                event.capitalize(), self.partner_id.email, self.name,
            )
            return True

        except Exception as e:
            # Don't raise error - the instance operation is complete,
            # the email is just a notification
            _logger.error(
                "Failed to send %s email for instance %s: %s",
                event, self.name, e,
                exc_info=True,
            )
            return False

    def action_suspend(self):
        """
        Suspendre l'instance (non-paiement, expiration).
        Suspend the instance (non-payment, expiration).
        """
        self.ensure_one()
        
        if self.state not in ['active']:
            raise UserError(_('Only active instances can be suspended.'))
        
        self.write({'state': 'suspended'})

        # Inform the agent to block access immediately
        self._send_expiration_to_instance(True, self.expiration_date)

        # Send suspension email to customer
        self._send_instance_email('suspended')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Instance Suspended'),
                'message': _('Instance %s has been suspended') % self.name,
                'type': 'warning',
                'sticky': False,
            }
        }

    def action_reactivate(self):
        """
        Réactiver une instance suspendue.
        Reactivate a suspended instance.
        """
        self.ensure_one()
        
        if self.state not in ['suspended', 'expired']:
            raise UserError(_('Only suspended or expired instances can be reactivated.'))
        
        self.write({'state': 'active'})

        # Lift suspension on the agent side
        self._send_expiration_to_instance(False, self.expiration_date)

        # Send reactivation email to customer
        self._send_instance_email('reactivated')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Instance Reactivated'),
                'message': _('Instance %s is now active') % self.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_terminate(self):
        """
        Terminer définitivement l'instance (supprime la DB).
        Terminate the instance permanently (deletes DB).
        
        Supprime la base de données PostgreSQL via l'API RPC.
        Deletes the PostgreSQL database via RPC API.

        Restricted to SaaS Administrator group only.
        """
        self.ensure_one()
        
        # Check if user is SaaS Administrator
        if not self.env.user.has_group('saas_manager.group_saas_admin'):
            raise UserError(
                _('Only SaaS Administrators can terminate instances.')
            )

        if self.state == 'terminated':
            raise UserError(_('Instance is already terminated.'))
        
        try:
            # Delete the PostgreSQL database via RPC
            self._delete_database()

            # Update instance state
            self.write({
                'state': 'terminated',
                'active': False,
            })

            _logger.info(f"Instance {self.name} ({self.database_name}) terminated successfully")

            # Send termination email to customer
            self._send_instance_email('terminated')

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Instance Terminated'),
                    'message': _('Instance %s has been terminated and database deleted') % self.name,
                    'type': 'success',
                    'sticky': False,
                }
            }
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Failed to terminate instance {self.name}: {str(e)}")
            raise UserError(
                _('Failed to terminate instance: %s') % str(e)
            )

    def _delete_database(self):
        """
        Supprimer la base de données PostgreSQL via l'API RPC.
        Delete the PostgreSQL database via RPC API.

        Uses the drop_database RPC service.

        Raises:
            UserError: If deletion fails
        """
        self.ensure_one()

        base_url = None

        try:
            # Get server details
            server = self.server_id
            base_url = server.server_url.rstrip('/')
            master_password = server.master_password

            _logger.info(f"Deleting database {self.database_name} on server {server.name}")
            _logger.info(f"Using server URL: {base_url}")

            # Endpoint for database operations
            rpc_url = f"{base_url}/jsonrpc"

            # Payload for dropping the database
            payload = {
                'jsonrpc': '2.0',
                'method': 'call',
                'params': {
                    'service': 'db',
                    'method': 'drop',
                    'args': [
                        master_password,        # master password
                        self.database_name,     # database name to drop
                    ]
                },
                'id': 1
            }

            _logger.info(f"Dropping database via RPC: {self.database_name}")

            # Make RPC call
            response = requests.post(
                rpc_url,
                json=payload,
                timeout=300,  # Allow up to 5 minutes for database deletion
                verify=self._ssl_verify,
            )

            response.raise_for_status()
            result = response.json()

            # Check for RPC errors
            if 'error' in result and result['error']:
                error_data = result['error'].get('data', {})
                error_msg = error_data.get('message', str(result['error']))
                _logger.warning(f"RPC Error: {error_msg}")
                raise UserError(
                    _("Failed to delete database via RPC.\n\nError: %s") % error_msg
                )

            _logger.info(f"Database {self.database_name} deleted successfully")
            return True

        except requests.exceptions.Timeout:
            _logger.error(f"Database deletion timed out for {self.database_name}")
            raise UserError(
                _("Database deletion timed out.\n\n"
                  "Please try again or contact support.")
            )
        except requests.exceptions.RequestException as e:
            _logger.exception(f"Request error during database deletion")
            raise UserError(
                _("Failed to connect to Odoo RPC endpoint.\n\n"
                  "URL: %s\n\n"
                  "Error: %s") % (base_url, str(e))
            )
        except UserError:
            raise
        except Exception as e:
            _logger.exception(f"Unexpected error in _delete_database")
            raise UserError(
                _("An unexpected error occurred while deleting the database.\n\nError: %s") % str(e)
            )

    def action_access_instance(self):
        """
        Ouvrir l'instance dans un nouvel onglet.
        Open instance in a new tab.
        
        Returns:
            dict: Action to open instance URL
        """
        self.ensure_one()
        
        if self.state not in ['active', 'suspended']:
            raise UserError(_('Instance must be active to access it.'))
        
        instance_url = f"{self.protocol}://{self.domain}"

        return {
            'type': 'ir.actions.act_url',
            'url': instance_url,
            'target': 'new',
        }

    @api.model
    def cron_check_subscription_expiry(self):
        """
        CRON: Vérifier les abonnements expirés et suspendre les instances.
        CRON: Check expired subscriptions and suspend instances.
        """
        _logger.info("Running subscription expiry check...")
        
        # Find instances with expired subscriptions
        expired_instances = self.search([
            ('state', '=', 'active'),
            ('expiration_date', '<=', fields.Datetime.now()),
        ])
        
        for instance in expired_instances:
            try:
                instance.action_suspend()  # sets state, notifies agent and emails customer
                _logger.info(f"Instance {instance.name} marked as suspended due to subscription expiry")

            except Exception as e:
                _logger.error(f"Failed to expire instance {instance.name}: {str(e)}")

    def action_sync_user_limit(self):
        """
        Manually sync user limit to instance.
        Called from button in form view.
        """
        self.ensure_one()
        
        if not self.domain:
            raise UserError(_('Instance has no domain configured.'))
        
        if self.state not in ['active', 'suspended']:
            raise UserError(_('Can only sync active or suspended instances.'))
        
        success = self._send_user_limit_to_instance()
        
        if success:
            self.write({
                'last_sync_date': fields.Datetime.now(),
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('User Limit Synced'),
                    'message': _('User limit of %d sent to instance successfully') % self.user_limit,
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise UserError(_(
                'Failed to sync user limit with instance. '
                'Check that saas_agent is installed in the instance and that the domain is accessible.'
            ))

    def action_refresh_users_count(self):
        """
        Refresh current users count from instance.
        Called from button in form view.
        """
        self.ensure_one()

        if self.state not in ['active', 'suspended']:
            raise UserError(_('Instance must be active or suspended.'))

        if not self.domain:
            raise UserError(_('Instance has no domain configured.'))

        count = self._get_users_count_from_instance()
        self.last_users_count = count
        percentage = (count / self.user_limit * 100) if self.user_limit else 0

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Users Count'),
                'message': _('%d users / %d limit (%.1f%%)') % (count, self.user_limit, percentage),
                'type': 'info',
                'sticky': False,
            }
        }

    def _ensure_agent_secret(self):
        self.ensure_one()
        if not self.agent_secret:
            self.agent_secret = self._generate_random_password(32)
        return self.agent_secret

    def _build_instance_url(self):
        protocol = getattr(self, 'protocol', 'https') or 'https'
        if self.domain and (self.domain.startswith('http://') or self.domain.startswith('https://')):
            return self.domain.rstrip('/')
        if self.domain:
            return f"{protocol}://{self.domain}"
        return None

    def _push_agent_secret_to_instance(self):
        """Push agent secret via /saas/bootstrap using server master password.

        No dependency on admin credentials — works even if the client
        changed their admin login/password.
        """
        self.ensure_one()
        base_url = self._build_instance_url()
        if not base_url:
            _logger.warning("No domain to push agent secret for %s", self.name)
            return False

        server = self.server_id
        if not server or not server.master_password:
            _logger.warning(
                "No master password configured on server %s",
                server.name if server else 'N/A',
            )
            return False

        secret = self._ensure_agent_secret()

        try:
            bootstrap_payload = {
                'master_password': server.master_password,
                'agent_secret': secret,
                'instance_uuid': self.database_name,
            }
            response = requests.post(
                f"{base_url}/saas/bootstrap",
                json={'jsonrpc': '2.0', 'params': bootstrap_payload},
                headers={'Content-Type': 'application/json'},
                timeout=30,
                verify=self._ssl_verify,
            )
            response.raise_for_status()
            payload = self._parse_agent_response(response)

            if payload.get('success'):
                _logger.info("Agent secret bootstrapped to %s via master password", self.name)
                return True

            _logger.warning(
                "Bootstrap agent secret failed for %s: %s",
                self.name, payload.get('error', 'Unknown error'),
            )
            return False

        except requests.exceptions.RequestException as exc:
            _logger.warning("Failed to bootstrap agent secret to %s: %s", self.name, exc)
            return False
        except Exception as exc:
            _logger.warning("Failed to push agent secret to %s: %s", self.name, exc)
            return False

    @property
    def _ssl_verify(self):
        return self.server_id.verify_ssl if self.server_id else True

    def _build_agent_jwt(self, action, extra=None, ttl=300):
        self.ensure_one()
        secret = self._ensure_agent_secret()
        now = int(time.time())
        payload = {
            'action': action,
            'db': self.database_name,
            'instance_uuid': self.database_name,
            'iat': now,
            'exp': now + ttl,
        }
        if extra:
            payload.update(extra)
        return jwt.encode(payload, secret, algorithm='HS256')

    def _call_agent(self, endpoint, token, timeout=15):
        base_url = self._build_instance_url()
        if not base_url:
            raise UserError(_('Instance has no domain configured.'))
        url = f"{base_url}{endpoint}"
        headers = {'Authorization': f'Bearer {token}'}
        return requests.post(url, json={'token': token}, headers=headers, timeout=timeout, verify=self._ssl_verify)

    def action_sso_login(self):
        """SSO login via JWT token — no admin credentials needed."""
        self.ensure_one()
        if self.state not in ['active', 'suspended']:
            raise UserError(_('Instance must be active to access it.'))

        if not self._push_agent_secret_to_instance():
            raise UserError(_(
                'Cannot sync agent secret with instance. '
                'Check that saas_agent is installed and the server master password is correct.'
            ))

        user_login = self.agent_impersonate_login or self.admin_login
        if not user_login or user_login.lower() in ('__system__', 'public'):
            raise UserError(_(
                'No SSO target login configured. Set the "SSO Login" field '
                'on the instance (system accounts cannot be impersonated).'
            ))
        token = self._build_agent_jwt('sso', {
            'user_login': user_login,
            'redirect': '/web',
        })

        base_url = self._build_instance_url()
        sso_url = f"{base_url}/saas/sso/jwt?token={token}"

        return {
            'type': 'ir.actions.act_url',
            'url': sso_url,
            'target': 'new',
        }

    def _send_user_limit_to_instance(self):
        self.ensure_one()

        if not self.domain or self.state not in ['active', 'suspended']:
            return False

        try:
            token = self._build_agent_jwt('set_user_limit', {'user_limit': self.user_limit})
            response = self._call_agent('/saas/set_user_limit', token)

            if response.status_code == 200:
                payload = self._parse_agent_response(response)

                if payload.get('success'):
                    _logger.info(
                        f"User limit synced to instance {self.name}:  "
                        f"{self.user_limit} users"
                    )
                    return True
                else:
                    _logger.error(
                        f"Failed to sync user limit to {self.name}: "
                        f"{payload.get('error', 'Unknown error')}"
                    )
                    return False
            else:
                _logger.warning(
                    f"HTTP {response.status_code} when syncing to {self.name}:  "
                    f"{response.text[: 200]}"
                )
                return False

        except requests.exceptions.RequestException as e:
            _logger.error(f"Network error syncing to instance {self.name}: {str(e)}")
            return False
        except Exception as e:
            _logger.error(f"Error syncing user limit to instance {self.name}: {str(e)}")
            return False

    def _get_users_count_from_instance(self):
        self.ensure_one()

        if not self.domain:
            return 0

        try:
            token = self._build_agent_jwt('get_users_count')
            response = self._call_agent('/saas/get_users_count', token)

            if response.status_code == 200:
                payload = self._parse_agent_response(response)

                if payload.get('success'):
                    return payload.get('current_users', 0)
                else:
                    _logger.warning(
                        f"Error getting user count from {self.name}: "
                        f"{payload.get('error', 'Unknown error')}"
                    )
                    return 0
            else:
                _logger.warning(
                    f"HTTP {response.status_code} when fetching users from {self.name}"
                )
                return 0

        except requests.exceptions.RequestException as e:
            _logger.debug(f"Network error fetching users from {self.name}: {str(e)}")
            return 0
        except Exception as e:
            _logger.error(f"Error getting user count from instance {self.name}: {str(e)}")
            return 0

    def cron_sync_all_user_limits(self):
        """
        CRON: Sync user limits to all active instances.
        Run this periodically to keep instances in sync.
        """
        instances = self.search([
            ('state', 'in', ['active', 'suspended']),
            ('domain', '!=', False),
        ])
        
        success_count = 0
        for instance in instances:
            try:
                instance.last_users_count = instance._get_users_count_from_instance()
                if instance._send_user_limit_to_instance():
                    success_count += 1
                    instance.write({'last_sync_date': fields.Datetime.now()})
            except Exception as e:
                _logger.error(f"Error syncing instance {instance.name}: {str(e)}")
                continue
        
        _logger.info(
            f"User limit sync completed: {success_count}/{len(instances)} instances synced"
        )

    @api.model
    def cron_check_user_limits(self):
        """
        CRON: Vérifier les limites d'utilisateurs et alerter.

        Seuils (config params) :
        - saas.user_limit_warn_percent  (défaut 80)  → message chatter
        - saas.user_limit_alert_percent (défaut 95)  → activity + email manager
        """
        _logger.info("Running user limit check...")

        ICP = self.env['ir.config_parameter'].sudo()
        warn_pct = float(ICP.get_param('saas.user_limit_warn_percent', '80') or 80)
        alert_pct = float(ICP.get_param('saas.user_limit_alert_percent', '95') or 95)

        admin_users = self._get_saas_admin_users()
        activity_type = 'saas_manager.mail_act_saas_alert'

        instances = self.search([
            ('state', 'in', ['active', 'suspended']),
            ('user_limit', '>', 0),
        ])

        for instance in instances:
            try:
                count = instance._get_users_count_from_instance()
                instance.write({'last_users_count': count})

                pct = (count / instance.user_limit) * 100

                if pct >= alert_pct:
                    body = _(
                        "User limit ALMOST EXCEEDED: %(count)d / %(limit)d users "
                        "(%(pct).0f%%) on instance %(name)s.",
                        count=count, limit=instance.user_limit, pct=pct, name=instance.name,
                    )
                    instance.message_post(
                        body=body,
                    )
                    for user in admin_users:
                        try:
                            instance.activity_schedule(
                                activity_type, user_id=user.id, note=body,
                            )
                        except Exception as act_exc:
                            _logger.warning(
                                "Could not schedule limit activity on %s: %s",
                                instance.name, act_exc,
                            )
                    _logger.warning("User limit alert for %s: %.0f%%", instance.name, pct)

                elif pct >= warn_pct:
                    instance.message_post(
                        body=_(
                            "User limit warning: %(count)d / %(limit)d users (%(pct).0f%%).",
                            count=count, limit=instance.user_limit, pct=pct,
                        ),
                    )
                    _logger.info("User limit warning for %s: %.0f%%", instance.name, pct)

            except Exception as e:
                _logger.error(f"Limit check failed for {instance.name}: {str(e)}")

        _logger.info("User limit check done: %d instances checked", len(instances))

    @api.model_create_multi
    def create(self, vals_list):
        """
        Créer une nouvelle instance SaaS.
        Create a new SaaS instance.

        Assure que partner_id est toujours défini avec l'utilisateur actuel par défaut.
        Ensures that partner_id is always set to the current user's partner by default.

        Args:
            vals_list (list): List of values for the new instances

        Returns:
            SaaSInstance: The created instances
        """
        Stage = self.env['saas.instance.stage']
        for vals in vals_list:
            if not vals.get('partner_id') and self.env.user.partner_id:
                vals['partner_id'] = self.env.user.partner_id.id
            if not vals.get('stage_id'):
                if vals.get('state'):
                    stage = self._stage_for_state(vals['state'])
                    if stage:
                        vals['stage_id'] = stage.id
                else:
                    default_stage_id = self._default_stage_id()
                    if default_stage_id:
                        vals['stage_id'] = default_stage_id
            if vals.get('stage_id') and not vals.get('state'):
                stage = Stage.browse(vals['stage_id'])
                if stage:
                    vals['state'] = stage.state

        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get('stage_sync_skip'):
            return super().write(vals)

        if 'stage_id' in vals and 'state' not in vals:
            stage = self.env['saas.instance.stage'].browse(vals['stage_id'])
            if stage:
                vals['state'] = stage.state

        res = super().write(vals)

        if 'state' in vals and 'stage_id' not in vals:
            for record in self:
                stage = record._stage_for_state(record.state)
                if stage and record.stage_id != stage:
                    record.with_context(stage_sync_skip=True).write({'stage_id': stage.id})

        return res

    def _parse_agent_response(self, response):
        data = response.json()
        # Odoo json type routes wrap payload in {'jsonrpc': '2.0', 'result': {...}}
        if isinstance(data, dict) and 'result' in data:
            payload = data.get('result') or {}
        else:
            payload = data
        if not isinstance(payload, dict):
            return {'success': False, 'error': _('Invalid agent response')}
        return payload

    def _send_expiration_to_instance(self, suspended, expiration_date=None):
        self.ensure_one()

        if not self.domain or self.state not in ['active', 'suspended']:
            return False

        payload = {'suspended': suspended}
        if expiration_date:
            payload['expiration_date'] = fields.Datetime.to_string(expiration_date)

        try:
            token = self._build_agent_jwt('set_expiration', payload)
            response = self._call_agent('/saas/set_expiration', token)

            if response.status_code == 200:
                data = self._parse_agent_response(response)
                if data.get('success'):
                    _logger.info(
                        "Expiration status synced to instance %s (suspended=%s)",
                        self.name,
                        suspended,
                    )
                    return True
                _logger.warning(
                    "Agent set_expiration error for %s: %s",
                    self.name,
                    data.get('error', 'Unknown error'),
                )
                return False

            _logger.warning(
                "HTTP %s when sending set_expiration to %s: %s",
                response.status_code,
                self.name,
                response.text[:200],
            )
            return False

        except requests.exceptions.RequestException as exc:
            _logger.error("Network error syncing expiration to %s: %s", self.name, exc)
            return False
        except Exception as exc:
            _logger.error("Error syncing expiration to %s: %s", self.name, exc)
            return False
