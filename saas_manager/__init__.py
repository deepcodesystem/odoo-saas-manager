# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import urllib3

# verify_ssl=False est un choix administrateur explicite (certificats
# auto-signés, environnements de test) : on évite le bruit InsecureRequestWarning.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from . import models
from . import controllers
