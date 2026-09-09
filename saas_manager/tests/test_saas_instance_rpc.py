# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Tests for SaaS Instance RPC User Limit Synchronization
"""

import requests
from unittest.mock import patch, MagicMock
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestSaaSInstanceRPC(TransactionCase):
    """Test cases for RPC user limit synchronization"""

    def setUp(self):
        """Set up test data"""
        super().setUp()

        # Create a test server
        self.server = self.env['saas.server'].create({
            'name': 'Test Server',
            'code': 'test-server-rpc',
            'server_url': 'http://localhost:8069',
            'server_ip': '127.0.0.1',
            'server_port': 8069,
            'db_host': 'localhost',
            'db_port': 5432,
            'db_user': 'odoo',
            'db_password': 'odoo',
            'master_password': 'test-master-pw',
            'cpu_cores': 4,
            'memory_gb': 16,
            'disk_gb': 500,
            'max_instances': 100,
            'state': 'active',
        })

        # Create a test template
        self.template = self.env['saas.template'].create({
            'name': 'Test Template',
            'code': 'test-template-rpc',
            'template_db': 'template_test_rpc',
            'server_id': self.server.id,
        })

        # Create a test partner
        self.partner = self.env['res.partner'].create({
            'name': 'Test Customer',
            'email': 'customer@example.com',
        })

        # Create a test instance
        self.instance = self.env['saas.instance'].create({
            'name': 'Test Instance',
            'partner_id': self.partner.id,
            'template_id': self.template.id,
            'server_id': self.server.id,
            'database_name': 'test_instance_db',
            'subdomain': 'test-instance-rpc',
            'admin_login': 'client-admin@example.com',
            'admin_password': 'test123',
            'user_limit': 10,
            'state': 'active',
        })

    def test_user_limit_field(self):
        """Test user_limit is settable and stored"""
        self.assertEqual(self.instance.user_limit, 10)

    def test_compute_users_percentage(self):
        """Test users percentage calculation"""
        # Simulate last synced count
        self.instance.last_users_count = 5
        self.instance._compute_current_users()
        self.assertEqual(self.instance.current_users, 5)

        # Calculate percentage
        self.instance._compute_users_percentage()
        self.assertEqual(self.instance.users_percentage, 50.0)

    def test_compute_users_percentage_zero_limit(self):
        """Test users percentage with zero limit"""
        # Temporarily set user_limit to 0
        self.instance.user_limit = 0
        self.instance._compute_users_percentage()
        self.assertEqual(self.instance.users_percentage, 0.0)

    def test_compute_current_users_no_rpc(self):
        """Compute must NOT trigger an RPC call (uses last_users_count)"""
        with patch.object(
            type(self.instance), '_get_users_count_from_instance'
        ) as mock_rpc:
            self.instance.last_users_count = 3
            self.instance._compute_current_users()
            self.assertEqual(self.instance.current_users, 3)
            mock_rpc.assert_not_called()

    @patch('requests.post')
    def test_send_user_limit_success(self, mock_post):
        """Test sending user limit to instance via RPC (success)"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True}
        mock_post.return_value = mock_response

        # Call the method
        result = self.instance._send_user_limit_to_instance()

        # Verify
        self.assertTrue(result)
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_send_user_limit_failure(self, mock_post):
        """Test sending user limit to instance via RPC (failure)"""
        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': False, 'error': 'Test error'}
        mock_post.return_value = mock_response

        # Call the method
        result = self.instance._send_user_limit_to_instance()

        # Verify
        self.assertFalse(result)

    @patch('requests.post')
    def test_send_user_limit_network_error(self, mock_post):
        """Test sending user limit with network error"""
        # Mock network error
        mock_post.side_effect = requests.exceptions.RequestException('Network error')

        # Call the method
        result = self.instance._send_user_limit_to_instance()

        # Verify
        self.assertFalse(result)

    @patch('requests.post')
    def test_get_users_count_success(self, mock_post):
        """Test getting users count from instance (success)"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True, 'current_users': 7}
        mock_post.return_value = mock_response

        # Call the method
        count = self.instance._get_users_count_from_instance()

        # Verify
        self.assertEqual(count, 7)

    @patch('requests.post')
    def test_get_users_count_failure(self, mock_post):
        """Test getting users count from instance (failure)"""
        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = 'Not found'
        mock_post.return_value = mock_response

        # Call the method
        count = self.instance._get_users_count_from_instance()

        # Verify
        self.assertEqual(count, 0)

    @patch('requests.post')
    def test_get_users_count_network_error(self, mock_post):
        """Test getting users count with network error"""
        # Mock network error
        mock_post.side_effect = requests.exceptions.RequestException('Network error')

        # Call the method
        count = self.instance._get_users_count_from_instance()

        # Verify
        self.assertEqual(count, 0)

    @patch('requests.post')
    def test_action_sync_user_limit_success(self, mock_post):
        """Test manual sync action (success)"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True}
        mock_post.return_value = mock_response

        # Call the action
        result = self.instance.action_sync_user_limit()

        # Verify
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')
        self.assertIsNotNone(self.instance.last_sync_date)

    @patch('requests.post')
    def test_action_sync_user_limit_failure(self, mock_post):
        """Test manual sync action (failure)"""
        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Server error'
        mock_post.return_value = mock_response

        # Call the action and expect error
        with self.assertRaises(UserError):
            self.instance.action_sync_user_limit()

    def test_action_sync_user_limit_no_domain(self):
        """Test manual sync action without domain"""
        # Remove the subdomain and domain via SQL (required/computed stored
        # fields, bypassed for the test)
        self.env.cr.execute(
            "UPDATE saas_instance SET subdomain = '', domain = '' WHERE id = %s",
            [self.instance.id],
        )
        self.instance.invalidate_recordset(['subdomain', 'domain'])
        # Force recompute of the stored computed domain from the empty subdomain
        self.env.add_to_compute(self.instance._fields['domain'], self.instance)
        self.env.flush_all()
        self.assertFalse(self.instance.domain)

        # Should raise error
        with self.assertRaises(UserError) as context:
            self.instance.action_sync_user_limit()

        self.assertIn('no domain', str(context.exception).lower())

    def test_action_sync_user_limit_wrong_state(self):
        """Test manual sync action with wrong state"""
        # Set instance to draft state
        self.instance.state = 'draft'

        # Should raise error
        with self.assertRaises(UserError) as context:
            self.instance.action_sync_user_limit()

        self.assertIn('active', str(context.exception).lower())

    @patch('requests.post')
    def test_cron_sync_all_user_limits(self, mock_post):
        """Test CRON job for syncing all instances"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True, 'current_users': 5}
        mock_post.return_value = mock_response

        # Create another active instance
        instance2 = self.env['saas.instance'].create({
            'name': 'Test Instance 2',
            'partner_id': self.partner.id,
            'template_id': self.template.id,
            'server_id': self.server.id,
            'database_name': 'test_instance_2_db',
            'subdomain': 'test-instance-2-cron',
            'admin_login': 'client-admin2@example.com',
            'admin_password': 'test123',
            'user_limit': 10,
            'state': 'active',
        })

        # Run CRON job
        self.env['saas.instance'].cron_sync_all_user_limits()

        # Verify both instances were synced
        self.assertIsNotNone(self.instance.last_sync_date)
        self.assertIsNotNone(instance2.last_sync_date)
        self.assertEqual(self.instance.last_users_count, 5)

    def test_inactive_instance_not_synced(self):
        """Test that inactive instances are not synced"""
        # Set instance to terminated state
        self.instance.state = 'terminated'

        # Try to sync
        result = self.instance._send_user_limit_to_instance()

        # Should return False without making request
        self.assertFalse(result)

    def test_compute_current_users_inactive_instance(self):
        """Test current users computation for inactive instance"""
        # Set instance to draft
        self.instance.state = 'draft'

        # Compute current users
        self.instance._compute_current_users()

        # Should be 0
        self.assertEqual(self.instance.current_users, 0)

    def test_sso_login_refused_without_target(self):
        """SSO login must refuse system accounts and empty targets"""
        self.env['ir.config_parameter'].sudo().set_param('saas.base_domain', 'example.com')
        self.instance.write({
            'admin_login': '__system__',
            'agent_impersonate_login': False,
        })
        with self.assertRaises(UserError):
            self.instance.action_sso_login()

    def test_sso_login_allows_client_admin(self):
        """SSO login must still allow the client admin account (uid 2)"""
        self.env['ir.config_parameter'].sudo().set_param('saas.base_domain', 'example.com')
        self.instance.write({
            'admin_login': 'admin',
            'agent_impersonate_login': False,
        })
        token_payload = None

        def fake_jwt_encode(payload, secret, algorithm='HS256'):
            nonlocal token_payload
            token_payload = payload
            return 'fake-token'

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True}

        with patch('odoo.addons.saas_manager.models.saas_instance.jwt.encode', side_effect=fake_jwt_encode), \
             patch('odoo.addons.saas_manager.models.saas_instance.requests.post', return_value=mock_response):
            action = self.instance.action_sso_login()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn('token=fake-token', action['url'])
        self.assertEqual(token_payload.get('user_login'), 'admin')

    def test_unique_constraints(self):
        """Database name and subdomain must be unique"""
        with self.assertRaises(Exception):
            self.env['saas.instance'].create({
                'name': 'Dup Instance',
                'partner_id': self.partner.id,
                'template_id': self.template.id,
                'server_id': self.server.id,
                'database_name': 'test_instance_db',  # duplicate
                'subdomain': 'dup-subdomain',
                'state': 'draft',
            })

    def test_master_password_not_default_admin(self):
        """New servers must not get a default 'admin' master password"""
        server = self.env['saas.server'].create({
            'name': 'No Default PW Server',
            'code': 'no-default-pw',
            'server_url': 'https://saas2.example.com',
        })
        self.assertFalse(server.master_password)
