# This file contains python variables that configure Lamson for email processing.
import sys
import logging
import os

# You may add additional parameters such as `username' and `password' if your
# relay server requires authentication, `starttls' (boolean) or `ssl' (boolean)
# for secure connections.
relay_config = {'host': os.getenv('RELAY_HOST', 'localhost'), 'port': 8825 }

receiver_config = {'host': 'localhost', 'port': 8823}

handlers = ['smtp_handler.main']

# router_defaults = {'host': '\*\\.mit\\.edu'}
router_defaults = {'host': '.+'}

template_config = {'dir': 'smtp_handler', 'module': 'templates'}

# hook django
import os
import django 
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "http_handler.settings")

django.setup()
# the config/boot.py will turn these values into variables set in settings
