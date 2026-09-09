# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Tests for SaaS Server Model
"""

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestSaaSServer(TransactionCase):
    """Test cases for saas.server model"""

    def setUp(self):
        """Set up test data"""
        super().setUp()
        self.server = self._create_server('test-server-1', 'http://localhost:8069')

    def _create_server(self, code, url, **kwargs):
        vals = {
            'name': 'Test Server %s' % code,
            'code': code,
            'server_url': url,
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
            'state': 'draft',
        }
        vals.update(kwargs)
        return self.env['saas.server'].create(vals)

    def _create_template(self, code, template_db, server):
        return self.env['saas.template'].create({
            'name': 'Test Template %s' % code,
            'code': code,
            'template_db': template_db,
            'server_id': server.id,
        })

    def _create_instance(self, suffix, template, server):
        partner = self.env['res.partner'].create({
            'name': 'Test Partner %s' % suffix,
        })
        return self.env['saas.instance'].create({
            'name': 'Test Instance %s' % suffix,
            'database_name': 'test_instance_%s' % suffix,
            'subdomain': 'test-%s' % suffix,
            'template_id': template.id,
            'server_id': server.id,
            'partner_id': partner.id,
        })

    def test_server_creation(self):
        """Test server creation"""
        self.assertIsNotNone(self.server)
        self.assertEqual(self.server.name, 'Test Server test-server-1')
        self.assertEqual(self.server.code, 'test-server-1')
        self.assertEqual(self.server.state, 'draft')

    def test_code_unique(self):
        """Test that server code must be unique"""
        with self.assertRaises(Exception):
            # Try to create a server with the same code
            self._create_server('test-server-1', 'http://another:8069')

    def test_server_url_unique(self):
        """Test that server URL must be unique"""
        with self.assertRaises(Exception):
            self._create_server('test-server-url-dup', 'http://localhost:8069')

    def test_code_lowercase(self):
        """Test that server code must be lowercase"""
        with self.assertRaises(ValidationError):
            self._create_server('InvalidCode', 'http://localhost-other:8069')

    def test_server_url_validation(self):
        """Test that server URL must start with http:// or https://"""
        with self.assertRaises(ValidationError):
            self._create_server('invalid-url', 'ftp://localhost:8069')

    def test_max_instances_validation(self):
        """Test that max_instances must be > 0"""
        with self.assertRaises(ValidationError):
            self._create_server('invalid-capacity', 'http://localhost-other2:8069', max_instances=0)

    def test_master_password_no_default(self):
        """New servers must not have a default master password"""
        server = self.env['saas.server'].create({
            'name': 'No Default PW',
            'code': 'no-default-pw',
            'server_url': 'https://saas-nopw.example.com',
        })
        self.assertFalse(server.master_password)

    def test_instance_count_compute(self):
        """Test that instance count is computed correctly"""
        template = self._create_template('test-template-cnt', 'test_template_db_cnt', self.server)
        self._create_instance('cnt1', template, self.server)
        self._create_instance('cnt2', template, self.server)

        # Refresh server
        self.server.invalidate_recordset()

        # Check instance count
        self.assertEqual(self.server.instance_count, 2)

    def test_available_capacity_compute(self):
        """Test that available capacity is computed correctly"""
        self.assertEqual(self.server.available_capacity, 100.0)  # 0/100 instances

    def test_is_online_compute(self):
        """Test that is_online is computed based on state"""
        # Initially draft, so not online
        self.assertFalse(self.server.is_online)

        # Activate server
        self.server.state = 'active'
        self.assertTrue(self.server.is_online)

        # Deactivate
        self.server.state = 'offline'
        self.assertFalse(self.server.is_online)

    def test_delete_server_with_instances_fails(self):
        """Test that cannot delete server with instances"""
        template = self._create_template('test-template-del', 'test_template_db_del', self.server)
        self._create_instance('del', template, self.server)

        # Try to delete server - should fail
        with self.assertRaises(UserError):
            self.server.unlink()

    def test_deactivate_server_with_instances_fails(self):
        """Test that cannot deactivate server with instances"""
        template = self._create_template('test-template-deact', 'test_template_db_deact', self.server)
        self._create_instance('deact', template, self.server)

        # Try to deactivate - should fail
        with self.assertRaises(UserError):
            self.server.action_deactivate()

    def test_get_available_server(self):
        """Test get_available_server method"""
        # Make server active and available
        self.server.state = 'active'
        self.server.max_instances = 100

        # Get available server
        available = self.env['saas.server'].get_available_server(min_capacity_percent=20)

        # Should return our server
        self.assertEqual(available.id, self.server.id)

    def test_get_available_server_no_capacity(self):
        """Test get_available_server fails when no capacity"""
        # Disable any other active server present in the database
        other_servers = self.env['saas.server'].search([('id', '!=', self.server.id)])
        other_servers.write({'state': 'disabled', 'active': False})

        # Make server full
        self.server.state = 'active'
        self.server.max_instances = 1

        template = self._create_template('test-template-full', 'test_template_db_full', self.server)
        self._create_instance('full', template, self.server)

        # Try to get available server - should fail
        with self.assertRaises(UserError):
            self.env['saas.server'].get_available_server(min_capacity_percent=20)
