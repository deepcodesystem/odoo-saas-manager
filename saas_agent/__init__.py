# -*- coding: utf-8 -*-
import urllib3

# Même justification que saas_manager : verify_ssl est configurable par serveur.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from . import controllers
from . import models
