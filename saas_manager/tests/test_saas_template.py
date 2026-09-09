# -*- coding: utf-8 -*-
"""
Tests pour la création et le clonage de templates SaaS

Test file for SaaS Template creation and cloning
"""

import logging
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TestSaaSTemplateCreation(TransactionCase):
    """Test cases for SaaS Template creation and provisioning"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_model = cls.env['saas.template']
        cls.server = cls.env['saas.server'].create({
            'name': 'Template Test Server',
            'code': 'template-test-server',
            'server_url': 'https://saas-template-test.example.com',
        })

    def _create_template(self, **kwargs):
        vals = {
            'server_id': self.server.id,
        }
        vals.update(kwargs)
        return self.template_model.create(vals)

    def test_create_template_record(self):
        """Test: Créer un enregistrement template"""
        template = self._create_template(**{
            'name': 'Test Template',
            'code': 'test_template',
            'template_db': 'template_test',
            'description': 'Template de test',
        })

        self.assertTrue(template.id)
        self.assertEqual(template.name, 'Test Template')
        self.assertEqual(template.code, 'test_template')
        self.assertFalse(template.is_template_ready)

    def test_template_code_must_be_lowercase(self):
        """Test: Le code template doit être en minuscules"""
        with self.assertRaises(Exception):
            self._create_template(**{
                'name': 'Invalid Template',
                'code': 'InvalidCode',  # Should be lowercase
                'template_db': 'template_invalid',
            })

    def test_template_db_unique(self):
        """Test: Le nom de la base template doit être unique"""
        self._create_template(**{
            'name': 'Template 1',
            'code': 'template1',
            'template_db': 'template_unique',
        })

        with self.assertRaises(Exception):
            self._create_template(**{
                'name': 'Template 2',
                'code': 'template2',
                'template_db': 'template_unique',  # Duplicate
            })

    def test_instance_count_computation(self):
        """Test: Le compte des instances est calculé correctement"""
        template = self._create_template(**{
            'name': 'Count Test',
            'code': 'count_test',
            'template_db': 'template_count',
        })

        # Vérifier le compte initial
        self.assertEqual(template.instance_count, 0)

    def test_version_increment(self):
        """Test: La version s'incrémente correctement"""
        template = self._create_template(**{
            'name': 'Version Test',
            'code': 'version_test',
            'template_db': 'template_version',
            'template_version': '1.0.0',
        })

        # Appeler action_update_template
        template.action_update_template()

        # Vérifier que la version a changé
        self.assertEqual(template.template_version, '1.0.1')

    def test_cannot_create_template_db_without_ready(self):
        """Test: Impossible de cloner un template non prêt"""
        template = self._create_template(**{
            'name': 'Not Ready',
            'code': 'not_ready',
            'template_db': 'template_not_ready',
            'is_template_ready': False,
        })

        with self.assertRaises(UserError):
            template.clone_template_db('new_instance_db')


class TestSaaSInstanceProvisioning(TransactionCase):
    """Test cases for SaaS Instance provisioning"""

    def test_create_instance_from_template(self):
        """Test: Créer une instance depuis un template"""
        # TODO: Implémentation Phase 2
        pass

    def test_instance_provisioning_flow(self):
        """Test: Flux complet de provisioning"""
        # TODO: Implémentation Phase 2
        pass


class TestSaaSConfiguration(TransactionCase):
    """Test cases for SaaS configuration parameters"""

    def test_base_domain_config(self):
        """Test: Configuration du domaine de base"""
        config = self.env['ir.config_parameter'].sudo()
        base_domain = config.get_param('saas.base_domain')

        self.assertTrue(base_domain)
        _logger.info(f"Base domain: {base_domain}")

    def test_odoo_host_config(self):
        """Test: Configuration de l'hôte Odoo"""
        config = self.env['ir.config_parameter'].sudo()
        odoo_host = config.get_param('saas.odoo_host')

        self.assertTrue(odoo_host)
        _logger.info(f"Odoo host: {odoo_host}")


# ============================================================================
# Exemples d'utilisation - Usage Examples
# ============================================================================

"""
EXEMPLE 1: Créer un template et initialiser la base de données
EXAMPLE 1: Create a template and initialize the database

    # En Python/XML
    template = env['saas.template'].create({
        'name': 'Restaurant SaaS',
        'code': 'restaurant',
        'template_db': 'template_restaurant',
        'description': 'Template pour restaurants',
    })
    
    # Créer la base de données PostgreSQL
    try:
        result = template.action_create_template_db()
        # Succès - base créée et prête
        print(result['params']['message'])
    except UserError as e:
        print(f"Erreur: {e}")

EXEMPLE 2: Cloner un template pour une nouvelle instance
EXAMPLE 2: Clone a template for a new instance

    template = env['saas.template'].browse(1)
    
    if not template.is_template_ready:
        print("Template not ready")
        return
    
    try:
        template.clone_template_db('client_restaurant_db')
        print("Instance cloned successfully in ~10 seconds")
    except UserError as e:
        print(f"Clone failed: {e}")

EXEMPLE 3: Voir toutes les instances d'un template
EXAMPLE 3: View all instances from a template

    template = env['saas.template'].browse(1)
    instances = template.action_view_instances()
    # Affiche toutes les instances créées depuis ce template

EXEMPLE 4: Accéder à la configuration d'un template
EXAMPLE 4: Access template configuration

    template = env['saas.template'].browse(1)
    action = template.action_access_template_db()
    # Ouvre la base de données template dans un nouvel onglet
"""

