# -*- coding: utf-8 -*-
import base64
import logging

from django.core.management.base import BaseCommand, CommandError
from smtp_handler.utils import *
from schema.models import *
from schema.youps import (FolderSchema, ImapAccount, MailbotMode, MessageSchema, EmailRule)
from datetime import datetime, timedelta
from browser.imap import *
from imapclient import IMAPClient
from engine.constants import *
from smtp_handler.Pile import *
import datetime
from http_handler.settings import WEBSITE, TEST_ACCOUNT_EMAIL, TEST_ACCOUNT_PASSWORD
from browser.sandbox import interpret_bypass_queue 

logger = logging.getLogger('youps')  # type: logging.Logger

class Command(BaseCommand):
    args = ''
    help = 'Process email'

    # Auto-send messages to our test email account
    def handle(self, *args, **options):
        if len(args) == 0:
            print ("give recipients address as an argument!")
            return

        to_addr = args[0]
        test_emails = [
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

        index = 1
        for t in test_emails:
            # TODO what about msg-id missing??
            send_email("#%d " % index + t['subject'].decode('utf-8'), t['from_addr'], to_addr, t['body_plain'], t['body_html'].decode('utf-8'))
            index = index + 1


        
        imapAccount = None
        imap = None

        # Auth to test email accountss
        try:
            imapAccount = ImapAccount.objects.get(email=email)
            auth_res = authenticate( imapAccount )
            if not auth_res['status']:
                raise ValueError('Something went wrong during authentication. Refresh and try again!')

            imap = auth_res['imap']  # noqa: F841 ignore unused
        except Exception, e:
            logger.exception("failed while logging into imap")
            return

        test_cases = [
            [ # test cases for #1 email
                {
                    'code': 'print (my_message.from_)',
                    'expected': 'test@youps.csail.mit.edu'
                }, 
            ],
            [

            ]
        ]            
            
        for msg_index in range(len(test_cases)):
            # TODO find msg-id of MessageSchema and pass it as 
            for case_index in range(len(test_cases[msg_index])):
                test_case = test_cases[case_index]
                test_case['msg-id'] = ''

                res = interpret_bypass_queue("MAILBOX HERE", test_case)

                # TODO "MSG-ID HERE" will be uid of DB 
                assert res['appended_log']["MSG-ID HERE"] == test_case['expected']

                print("SUCCESS #%d %s - case #%d" % ((msg_index+1), test_emails[msg_index]['subject'], case_index))


        try:
            #TODO fix here 
            for folder_name in folder_names:
                messages = MessageSchema.objects.filter(imap_account=imapAccount, folder__name=folder_name).order_by("-base_message__date")[:N]

                for message_schema in messages:
                    assert isinstance(message_schema, MessageSchema)
                    mailbox = MailBox(imapAccount, imap, is_simulate=True)
                    imap_res = interpret_bypass_queue(mailbox, extra_info={'code': code, 'msg-id': message_schema.id})
                    logger.debug(imap_res)

                    message = Message(message_schema, imap)

                    from_field = None
                    if message.from_:
                        from_field = {
                            "name": message.from_.name,
                            "email": message.from_.email,
                            "organization": message.from_.organization,
                            "geolocation": message.from_.geolocation
                        }
                        
                    to_field = [{
                        "name": tt.name,
                        "email": tt.email,
                        "organization": tt.organization,
                        "geolocation": tt.geolocation
                    } for tt in message.to]

                    cc_field = [{
                        "name": tt.name,
                        "email": tt.email,
                        "organization": tt.organization,
                        "geolocation": tt.geolocation
                    } for tt in message.cc]

                    # TODO attach activated line
                    # This is to log for users
                    new_msg = {
                        "timestamp": str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f")), 
                        "type": "new_message", 
                        "folder": message.folder.name, 
                        "from_": from_field, 
                        "subject": message.subject, 
                        "to": to_field,
                        "cc": cc_field,
                        "flags": [f.encode('utf8', 'replace') for f in message.flags],
                        "date": str(message.date),
                        "deadline": str(message.deadline), 
                        "is_read": message.is_read, 
                        "is_deleted": message.is_deleted, 
                        "is_recent": message.is_recent,
                        "log": imap_res['appended_log'][message_schema.id]['log'],
                        "error": imap_res['appended_log'][message_schema.id]['error'] if 'error' in imap_res['appended_log'][message_schema.id] else False
                    }
                    

                    res['messages'][message_schema.id] = new_msg
            
            res['status'] = True
        except ImapAccount.DoesNotExist:
            logger.exception("failed while doing a user code run")
            res['code'] = "Not logged into IMAP"
        except FolderSchema.DoesNotExist:
            logger.exception("failed while doing a user code run")
            logger.debug("Folder is not found, but it should exist!")
        except Exception, e:
            logger.exception("failed while doing a user code run %s %s " % (e, traceback.format_exc()))
            res['code'] = msg_code['UNKNOWN_ERROR']
        finally:
            imap.logout()