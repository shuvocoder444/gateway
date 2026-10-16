import os
import sys

# cPanel Phusion Passenger WSGI entry point
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from gateway.environment import load_environment

load_environment()

# Ensure Python 3.12 virtualenv site-packages is in sys.path
venv_site_packages = "/home/webkoders/virtualenv/payment.webkoders.com/3.12/lib/python3.12/site-packages"
if os.path.exists(venv_site_packages) and venv_site_packages not in sys.path:
    sys.path.insert(0, venv_site_packages)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gateway.settings")

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

