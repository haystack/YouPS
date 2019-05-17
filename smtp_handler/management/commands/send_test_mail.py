# -*- coding: utf-8 -*-
import base64

from django.core.management.base import BaseCommand, CommandError
from smtp_handler.utils import *
from schema.models import *
from schema.youps import ImapAccount
from datetime import datetime, timedelta
from browser.imap import *
from imapclient import IMAPClient
from engine.constants import *
from smtp_handler.Pile import *
import datetime
from http_handler.settings import WEBSITE

class Command(BaseCommand):
    args = ''
    help = 'Process email'

    # Auto-send messages to the given email address
    def handle(self, *args, **options):
        if len(args) == 0:
            print "give recipients address as an argument!"
            return

        to_addr = args[0]
        test_cases = [
            {
                'subject': 'test email %s ' % str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f")),
                'from_addr': 'test@youps.csail.mit.edu',
                'body_plain': 'hello world',
                'body_html': 'hi'
            },
            {
                'subject': 'test email with emoji 🤷‍♀️ %s ' % str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f")),
                'from_addr': 'test@youps.csail.mit.edu',
                'body_plain': 'hello world',
                'body_html': '😎'
            },
        ]

        for t in test_cases:
            send_email(t['subject'].decode('utf-8'), t['from_addr'], to_addr, t['body_plain'], t['body_html'].decode('utf-8'))

                    
            
