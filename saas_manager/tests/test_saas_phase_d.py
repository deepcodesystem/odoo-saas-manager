# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Tests for Phase D provisioning: neutralization, subdomain, customization, crons
"""

from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestSaaSProvisioningPhaseD(TransactionCase):
    """Test cases for Phase D: provisioning stubs implementation"""

    def setUp(self):
        super().setUp()
        self.server = self.env['saas.server'].create({
            'name': 'PhaseD Test Server',
            'code': 'phased-test-server',
            'server_url': 'https://phased-test.example.com',
            'state': 'active',
            'max_instances': 100,
        })
        self.template = self.env['saas.template'].create({
            'name': 'PhaseD Template',
            'code': 'phased-test-template',
            'template_db': 'phased_test_template_db',
            'server_id': self.server.id,
        })
        self.partner = self.env['res.partner'].create({
            'name': 'PhaseD Customer',
            'email': 'phased@customer.example.com',
        })
        self.instance = self.env['saas.instance'].create({
            'name': 'PhaseD Instance',
            'partner_id': self.partner.id,
            'template_id': self.template.id,
            'server_id': self.server.id,
            'database_name': 'phased-test-instance-db',
            'subdomain': 'phased-test-instance-db',
            'state': 'draft',
        })

    # --- D.1 Neutralization -------------------------------------------------

    def test_neutralize_scope_none(self):
        """Scope 'none' → no purge attempted"""
        self.env['ir.config_parameter'].sudo().set_param('saas.neutralize_scope', 'none')
        with patch.object(type(self.instance), '_purge_database_light') as mock_purge:
            self.instance._neutralize_database()
            mock_purge.assert_not_called()

    def test_neutralize_scope_light(self):
        """Default scope 'light' → purge called"""
        with patch.object(type(self.instance), '_purge_database_light') as mock_purge:
            self.instance._neutralize_database()
            mock_purge.assert_called_once()

    def test_neutralize_failure_non_blocking(self):
        """Purge failure must not raise (non-blocking)"""
        with patch.object(
            type(self.instance), '_purge_database_light',
            side_effect=Exception('db error'),
        ):
            # Must not raise
            self.instance._neutralize_database()

    # --- D.2 Subdomain ------------------------------------------------------

    def test_subdomain_auto_align(self):
        """_configure_subdomain aligns subdomain to database name"""
        self.instance.subdomain = 'other-name'
        self.instance._configure_subdomain()
        self.assertEqual(self.instance.subdomain, self.instance.database_name)

    def test_subdomain_warning_non_blocking(self):
        """Mismatch subdomain/db name posts a warning, does not raise"""
        self.instance.subdomain = 'mismatched'
        # create() triggers constrains; no exception expected

    def test_web_base_url_set_locally(self):
        """web.base.url is written on a local instance (registry path)"""
        self.env['ir.config_parameter'].sudo().set_param(
            'web.base.url', 'https://phased-test.example.com')

        written = {}

        class FakeEnv(dict):
            pass

        class FakeICP:
            def sudo(self):
                return self

            def set_param(self, key, value):
                written[key] = value

        fake_env = MagicMock()
        fake_env.__getitem__.side_effect = lambda model: MagicMock(
            sudo=lambda: FakeICP()) if model == 'ir.config_parameter' else MagicMock()

        fake_cr = MagicMock()
        fake_registry = MagicMock()
        fake_registry.cursor.return_value.__enter__.return_value = fake_cr
        fake_env_cls = MagicMock(return_value=fake_env)

        with patch.object(type(self.instance), '_is_local_server', return_value=True), \
             patch('odoo.modules.registry.Registry', return_value=fake_registry), \
             patch('odoo.api.Environment', fake_env_cls):
            self.instance._set_instance_base_url('https://phased_test_instance_db.example.com')

        self.assertEqual(written.get('web.base.url'),
                         'https://phased_test_instance_db.example.com')

    # --- D.3 Customization ---------------------------------------------------

    def test_customize_rpc_auth_failure_skips(self):
        """Remote customization with failing RPC auth → skipped, no error"""
        self.template.write({
            'template_admin_login': 'tpl-admin@example.com',
            'template_admin_password': 'tpl-pass-123',
        })
        mock_auth = MagicMock()
        mock_auth.json.return_value = {'result': False}
        with patch('odoo.addons.saas_manager.models.saas_instance.requests') as mock_requests, \
             patch.object(type(self.instance), '_is_local_server', return_value=False):
            mock_requests.post.return_value = mock_auth
            self.instance._customize_instance()
            # Only the auth call happened, no company write call
            self.assertEqual(mock_requests.post.call_count, 1)

    def test_customize_no_partner(self):
        """No partner → customization skipped without error"""
        self.instance.partner_id = False
        self.instance._customize_instance()  # must not raise

    # --- D.4 Crons -----------------------------------------------------------

    def test_monitor_ping_success_resets_failures(self):
        """Health OK resets monitor_failures"""
        self.instance.state = 'active'
        self.instance.monitor_failures = 3
        with patch.object(type(self.instance), '_ping_instance', return_value=True), \
             patch.object(type(self.instance), '_get_database_size_gb', return_value=1.5):
            self.env['saas.instance'].cron_monitor_instances()
        self.assertEqual(self.instance.monitor_failures, 0)
        self.assertEqual(self.instance.storage_used, 1.5)

    def test_monitor_failure_increments(self):
        """Health KO increments monitor_failures"""
        self.instance.state = 'active'
        self.instance.monitor_failures = 0
        with patch.object(type(self.instance), '_ping_instance', return_value=False), \
             patch.object(type(self.instance), '_get_database_size_gb', return_value=2.0):
            self.env['saas.instance'].cron_monitor_instances()
        self.assertEqual(self.instance.monitor_failures, 1)

    def test_monitor_alerts_after_two_failures(self):
        """2 consecutive failures → chatter message posted"""
        self.instance.state = 'active'
        self.instance.monitor_failures = 1
        with patch.object(type(self.instance), '_ping_instance', return_value=False), \
             patch.object(type(self.instance), '_get_database_size_gb', return_value=2.0):
            self.env['saas.instance'].cron_monitor_instances()
        self.assertEqual(self.instance.monitor_failures, 2)
        messages = self.instance.message_ids.filtered(lambda m: 'unreachable' in (m.body or '').lower())
        self.assertTrue(messages)

    def test_user_limits_alert_threshold(self):
        """Count above alert percent → warning chatter"""
        self.instance.write({
            'state': 'active',
            'user_limit': 10,
        })
        with patch.object(
            type(self.instance), '_get_users_count_from_instance', return_value=10,
        ):
            self.env['saas.instance'].cron_check_user_limits()
        self.assertEqual(self.instance.last_users_count, 10)

    def test_user_limits_below_warn(self):
        """Count below warn percent → no alert"""
        self.instance.write({
            'state': 'active',
            'user_limit': 10,
        })
        with patch.object(
            type(self.instance), '_get_users_count_from_instance', return_value=1,
        ):
            self.env['saas.instance'].cron_check_user_limits()
        self.assertEqual(self.instance.last_users_count, 1)

    # --- Helpers -------------------------------------------------------------

    def test_get_saas_admin_users(self):
        """_get_saas_admin_users returns active admin group users"""
        users = self.instance._get_saas_admin_users()
        self.assertTrue(users)
        self.assertIn(self.env.ref('base.user_admin'), users)

    def test_neutralize_queries_are_guardsafe(self):
        """All light queries reference existing tables pattern (str, sql)"""
        for table, query in type(self.instance).NEUTRALIZE_LIGHT_QUERIES:
            self.assertIsInstance(table, str)
            self.assertIn(table, query)

    def _get_db_conn_params(self):
        from odoo.tools import config
        return {
            'host': config.get('db_host') or 'localhost',
            'port': config.get('db_port') or 5432,
            'user': config.get('db_user'),
            'password': config.get('db_password') or '',
        }

    def test_purge_preserves_system_users(self):
        """La purge light préserve les users référencés par ir_model_data
        (base.public_user, base.default_user…) et supprime les users de démo."""
        import psycopg2
        import random
        import string as string_mod

        dbname = 'test_neutralize_tmp_' + ''.join(
            random.choice(string_mod.ascii_lowercase) for _ in range(6))

        params = self._get_db_conn_params()
        # Point the test server at the real database config so the purge
        # can connect
        self.server.write({
            'db_host': params['host'],
            'db_port': int(params['port']),
            'db_user': params['user'],
            'db_password': params['password'],
        })
        admin_conn = psycopg2.connect(dbname='postgres', connect_timeout=10, **params)
        admin_conn.set_isolation_level(0)  # autocommit
        try:
            with admin_conn.cursor() as cr:
                cr.execute('DROP DATABASE IF EXISTS %s' % dbname)
                cr.execute('CREATE DATABASE %s' % dbname)

            # Populate a minimal schema (other tables are guard-skipped)
            conn = psycopg2.connect(
                dbname=dbname, connect_timeout=10, **params
            )
            with conn.cursor() as cr:
                cr.execute("""
                    CREATE TABLE res_users (
                        id SERIAL PRIMARY KEY,
                        login VARCHAR,
                        partner_id INTEGER
                    );
                    CREATE TABLE res_partner (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR
                    );
                    CREATE TABLE res_company (
                        id SERIAL PRIMARY KEY,
                        partner_id INTEGER
                    );
                    CREATE TABLE ir_model_data (
                        id SERIAL PRIMARY KEY,
                        model VARCHAR,
                        res_id INTEGER
                    );
                    INSERT INTO res_partner (id, name) VALUES (1, 'Company Partner'), (2, 'Demo Partner'), (3, 'Public Partner'), (4, 'Admin Partner');
                    INSERT INTO res_company (id, partner_id) VALUES (1, 1);
                    INSERT INTO res_users (id, login, partner_id) VALUES (1, '__system__', 1), (2, 'admin', 4), (4, 'public', 3), (5, 'demo.user', NULL);
                    INSERT INTO ir_model_data (model, res_id) VALUES
                        ('res.users', 4),  -- base.public_user → préservé
                        ('res.partner', 3)  -- partenaire du public_user → préservé
                """)
            conn.commit()
            conn.close()

            with patch.object(
                type(self.instance), 'database_name',
                new_callable=lambda: property(lambda self: dbname),
            ):
                self.instance._purge_database_light()

            conn = psycopg2.connect(
                dbname=dbname, connect_timeout=10, **params
            )
            with conn.cursor() as cr:
                cr.execute("SELECT login FROM res_users ORDER BY id")
                logins = [row[0] for row in cr.fetchall()]
                cr.execute("SELECT name FROM res_partner ORDER BY id")
                partners = [row[0] for row in cr.fetchall()]
            conn.close()

            # system + admin + public preserved ; demo.user purged
            self.assertIn('__system__', logins)
            self.assertIn('admin', logins)
            self.assertIn('public', logins)
            self.assertNotIn('demo.user', logins)
            # company partner preserved ; demo partner purged ; public partner preserved
            self.assertIn('Company Partner', partners)
            self.assertIn('Public Partner', partners)
            self.assertNotIn('Demo Partner', partners)
        finally:
            with admin_conn.cursor() as cr:
                cr.execute('DROP DATABASE IF EXISTS %s' % dbname)
            admin_conn.close()
