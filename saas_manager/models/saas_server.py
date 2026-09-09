# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
SaaS Server Model
=================
Gestion des serveurs Odoo multi-tenant.
Management of multi-tenant Odoo servers.
"""

import logging
import requests
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SaaSServer(models.Model):
    """
    SaaS Server - Multi-tenant Odoo Server Management

    Représente un serveur Odoo dédié qui hébège plusieurs instances SaaS.

    Represents a dedicated Odoo server that hosts multiple SaaS instances.
    """
    _name = 'saas.server'
    _description = 'SaaS Server'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    # Basic Information
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help="Display order"
    )
    name = fields.Char(
        string='Server Name',
        required=True,
        tracking=True,
        help="Server name (e.g., 'Production Server 1')"
    )
    code = fields.Char(
        string='Server Code',
        required=True,
        tracking=True,
        help="Technical code for the server (e.g., 'prod-1')"
    )
    description = fields.Text(
        string='Description',
        help="Server description and notes"
    )

    # Server Configuration
    server_url = fields.Char(
        string='Server URL',
        required=True,
        tracking=True,
        help="Base URL of the server (e.g., 'https://saas1.example.com')"
    )
    instance_protocol = fields.Selection([
        ('http', 'HTTP'),
        ('https', 'HTTPS'),
    ], string='Instance Protocol', default='https', required=True,
        tracking=True,
        help="Protocole utilisé pour les URLs des instances hébergées sur ce serveur. "
             "Utiliser HTTP pour les environnements locaux/de développement."
    )
    server_ip = fields.Char(
        string='Server IP Address',
        help="Server IP address for direct connection"
    )
    server_port = fields.Integer(
        string='Server Port',
        default=8069,
        help="Odoo server port"
    )
    server_username = fields.Char(
        string='Server Username',
        help="SSH/Connection username for server management"
    )
    server_password = fields.Char(
        string='Server Password',
        help="SSH/Connection password (encrypted)"
    )

    # Database Configuration
    db_host = fields.Char(
        string='Database Host',
        default='localhost',
        help="PostgreSQL database host"
    )
    db_port = fields.Integer(
        string='Database Port',
        default=5432,
        help="PostgreSQL database port"
    )
    db_user = fields.Char(
        string='Database User',
        default='odoo',
        help="PostgreSQL database user"
    )
    db_password = fields.Char(
        string='Database Password',
        help="PostgreSQL database password (encrypted)"
    )
    master_password = fields.Char(
        string='Master Password',
        help="Odoo master password for database operations. "
             "Required to provision/terminate instances on this server.",
        copy=False,
    )
    verify_ssl = fields.Boolean(
        string='Vérifier SSL',
        default=True,
        help="Vérifier le certificat SSL lors des appels HTTP vers ce serveur. "
             "Désactiver uniquement pour les certificats auto-signés ou les environnements de test."
    )

    # Server Resources
    cpu_cores = fields.Integer(
        string='CPU Cores',
        help="Number of CPU cores available"
    )
    memory_gb = fields.Integer(
        string='Memory (GB)',
        help="Total available memory in GB"
    )
    disk_gb = fields.Integer(
        string='Disk Space (GB)',
        help="Total disk space in GB"
    )

    # Server Status
    state = fields.Selection(
        string='Status',
        selection=[
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('maintenance', 'Maintenance'),
            ('offline', 'Offline'),
            ('disabled', 'Disabled'),
        ],
        default='draft',
        tracking=True,
        help="Server current status"
    )
    is_online = fields.Boolean(
        string='Is Online',
        default=False,
        compute='_compute_is_online',
        help="Server online status"
    )
    last_check_date = fields.Datetime(
        string='Last Health Check',
        readonly=True,
        help="Last server health check timestamp"
    )
    health_status = fields.Selection(
        string='Health Status',
        selection=[
            ('healthy', 'Healthy'),
            ('warning', 'Warning'),
            ('critical', 'Critical'),
            ('unknown', 'Unknown'),
        ],
        default='unknown',
        readonly=True,
        help="Server health status"
    )

    # Capacity Management
    max_instances = fields.Integer(
        string='Max Instances',
        default=100,
        help="Maximum number of instances this server can host"
    )
    instance_count = fields.Integer(
        string='Current Instances',
        compute='_compute_instance_count',
        readonly=True,
        help="Number of instances currently hosted"
    )
    available_capacity = fields.Float(
        string="Capacité disponible (%)",
        compute='_compute_available_capacity',
        store=True,  # Ajouter store=True
        compute_sudo=True
    )

    # Relationships
    instance_ids = fields.One2many(
        'saas.instance',
        'server_id',
        string='Hosted Instances',
        help="Instances hosted on this server"
    )

    # Flags
    active = fields.Boolean(
        string='Active',
        default=True
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Server code must be unique!'),
        ('server_url_unique', 'UNIQUE(server_url)', 'Server URL must be unique!'),
    ]

    @api.onchange('server_url')
    def _onchange_server_url_protocol(self):
        """Auto-détecter le protocole depuis l'URL du serveur."""
        if self.server_url and not self.instance_protocol:
            self.instance_protocol = 'http' if self.server_url.startswith('http://') else 'https'

    @api.constrains('code')
    def _check_code(self):
        """
        Valider le format du code technique.
        Validate technical code format.
        """
        for server in self:
            if server.code and not server.code.islower():
                raise ValidationError(_('Server code must be lowercase.'))

    @api.constrains('server_url')
    def _check_server_url(self):
        """
        Valider le format de l'URL du serveur.
        Validate server URL format.
        """
        for server in self:
            if server.server_url:
                if not server.server_url.startswith(('http://', 'https://')):
                    raise ValidationError(
                        _('Server URL must start with http:// or https://')
                    )

    @api.constrains('max_instances')
    def _check_max_instances(self):
        """
        Valider que max_instances est positif.
        Validate max_instances is positive.
        """
        for server in self:
            if server.max_instances <= 0:
                raise ValidationError(
                    _('Maximum instances must be greater than 0.')
                )

    @api.depends('state')
    def _compute_is_online(self):
        """
        Déterminer si le serveur est en ligne.
        Determine if the server is online.
        """
        for server in self:
            server.is_online = server.state == 'active'

    @api.depends('instance_ids')
    def _compute_instance_count(self):
        """
        Compter le nombre d'instances actuelles.
        Count current number of instances.
        """
        for server in self:
            server.instance_count = len(server.instance_ids)

    @api.depends('max_instances', 'instance_count')
    def _compute_available_capacity(self):
        """
        Calculer le pourcentage de capacité disponible.
        Calculate available capacity percentage.
        """
        for server in self:
            if server.max_instances > 0:
                used = server.instance_count
                server.available_capacity = ((server.max_instances - used) / server.max_instances) * 100
            else:
                server.available_capacity = 0.0

    def _test_connection(self):
        """
        Tester la connexion au serveur via RPC.
        Test server connection via RPC.

        Returns:
            bool: True if connection successful
        """
        self.ensure_one()
        rpc_url = None

        try:
            # Nettoyer l'URL de base (sans le chemin)
            base_url = self.server_url.rstrip('/')

            # Tester la connexion en accédant à un endpoint simple
            # plutôt que de faire un appel RPC complexe
            test_url = f"{base_url}/web/health"

            _logger.info(f"Testing connection to server {self.name}: {test_url}")

            response = requests.get(
                test_url,
                timeout=10,
                verify=self.verify_ssl,
                allow_redirects=True
            )

            # Si la réponse HTTP 200 ou 404 (page existe mais pas trouvée), le serveur répond
            # Si c'est un 302 redirect, c'est aussi bon signe
            if response.status_code in [200, 301, 302, 303, 307, 308, 404]:
                _logger.info(f"Connection to server {self.name} successful. Status: {response.status_code}")
                return True
            else:
                _logger.warning(f"Server {self.name} returned HTTP {response.status_code}. URL: {test_url}")
                return False

        except requests.exceptions.Timeout:
            _logger.warning(f"Connection to server {self.name} timed out (10s). URL: {base_url}")
            return False
        except requests.exceptions.ConnectionError as e:
            _logger.warning(f"Could not connect to server {self.name}. URL: {base_url}. Error: {str(e)}")
            return False
        except requests.exceptions.RequestException as e:
            _logger.warning(f"Request error connecting to server {self.name}: {str(e)}")
            return False
        except Exception as e:
            _logger.warning(f"Error testing connection to server {self.name}: {str(e)}")
            return False

    def action_check_health(self):
        """
        Vérifier l'état de santé du serveur.
        Check server health status.

        Returns:
            dict: Action result
        """
        self.ensure_one()

        try:
            is_online = self._test_connection()

            if is_online:
                health_status = 'healthy'
                new_state = 'active'
            else:
                health_status = 'critical'
                new_state = 'offline'

            self.write({
                'health_status': health_status,
                'last_check_date': datetime.now(),
                'state': new_state,
            })

            message = _('Server is %s') % ('ONLINE' if is_online else 'OFFLINE')
            notification_type = 'success' if is_online else 'danger'

        except Exception as e:
            _logger.exception("Error checking server health")
            health_status = 'critical'
            self.write({
                'health_status': health_status,
                'last_check_date': datetime.now(),
                'state': 'offline',
            })
            message = _('Health check failed: %s') % str(e)
            notification_type = 'danger'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Health Check Result'),
                'message': message,
                'type': notification_type,
                'sticky': False,
            }
        }

    def action_activate(self):
        """
        Activer le serveur.
        Activate the server.

        Returns:
            dict: Action result
        """
        self.ensure_one()

        # Test connection before activating
        if not self._test_connection():
            raise UserError(
                _("Cannot activate server. Connection test failed.\n\n"
                  "Please check the server URL and ensure the server is online.")
            )

        self.write({
            'state': 'active',
            'health_status': 'healthy',
            'last_check_date': datetime.now(),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Server Activated'),
                'message': _('Server "%s" has been activated.') % self.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_deactivate(self):
        """
        Désactiver le serveur.
        Deactivate the server.

        Returns:
            dict: Action result
        """
        self.ensure_one()

        if self.instance_ids:
            raise UserError(
                _("Cannot deactivate server while it has instances.\n\n"
                  "Please migrate or delete all instances first.")
            )

        self.write({
            'state': 'disabled',
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Server Deactivated'),
                'message': _('Server "%s" has been deactivated.') % self.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_maintenance(self):
        """
        Mettre le serveur en maintenance.
        Put server in maintenance mode.

        Returns:
            dict: Action result
        """
        self.ensure_one()

        self.write({
            'state': 'maintenance',
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Maintenance Mode'),
                'message': _('Server "%s" is now in maintenance mode.') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }

    def action_view_instances(self):
        """
        Voir toutes les instances hébergées sur ce serveur.
        View all instances hosted on this server.

        Returns:
            dict: Action to display instances
        """
        self.ensure_one()

        return {
            'name': _('Instances on %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'saas.instance',
            'view_mode': 'list,form,kanban',
            'domain': [('server_id', '=', self.id)],
            'context': {'default_server_id': self.id},
        }

    def action_test_connection(self):
        """
        Tester la connexion au serveur.
        Test connection to the server.

        Returns:
            dict: Action result
        """
        self.ensure_one()

        try:
            is_online = self._test_connection()

            if is_online:
                message = _('Connection to server "%s" is successful!') % self.name
                notification_type = 'success'
            else:
                message = _('Failed to connect to server "%s".\n\nPlease check:\n- Server URL: %s\n- Server Port: %s\n- Server is running') % (self.name, self.server_url, self.server_port)
                notification_type = 'danger'
        except Exception as e:
            message = _('Connection test error: %s') % str(e)
            notification_type = 'danger'
            _logger.exception(f"Connection test error for server {self.name}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Connection Test'),
                'message': message,
                'type': notification_type,
                'sticky': False,
            }
        }

    def get_available_server(self, min_capacity_percent=20):
        """
        Obtenir un serveur disponible avec suffisamment de capacité.
        Get an available server with sufficient capacity.

        Args:
            min_capacity_percent (float): Minimum required capacity percentage

        Returns:
            saas.server: The best available server

        Raises:
            UserError: If no available server found
        """
        available_servers = self.search([
            ('state', '=', 'active'),
            ('available_capacity', '>=', min_capacity_percent),
        ], order='available_capacity DESC')

        if not available_servers:
            raise UserError(
                _("No available server found with at least %d%% capacity.\n\n"
                  "Please add more servers or increase maximum instances.") % min_capacity_percent
            )

        # Return the server with the most available capacity
        return available_servers[0]

    @api.model
    def cron_check_all_servers_health(self):
        """
        CRON: Vérifier la santé de tous les serveurs actifs.
        CRON: Check health of all active servers.
        """
        _logger.info("Running server health check...")
        
        servers = self.search([('state', 'in', ['active', 'maintenance'])])
        
        for server in servers:
            try:
                server.action_check_health()
            except Exception as e:
                _logger.error(f"Health check failed for server {server.name}: {str(e)}")

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to add additional logic.
        """
        records = super().create(vals_list)
        for record in records:
            _logger.info(f"New SaaS server created: {record.name} ({record.code})")
        return records

    def write(self, vals):
        """
        Override write to add additional logic.
        """
        if 'state' in vals:
            _logger.info(f"Server {self.name} state changed to: {vals['state']}")
        return super().write(vals)

    def unlink(self):
        """
        Override unlink to prevent deletion of servers with instances.
        """
        for server in self:
            if server.instance_ids:
                raise UserError(
                    _("Cannot delete server '%s' while it has instances.\n\n"
                      "Please migrate or delete all instances first.") % server.name
                )
        return super().unlink()

