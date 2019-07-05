# encoding: utf-8
import base64
import logging
import traceback

from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail
from smtp_handler.utils import *
from schema.models import *
from schema.youps import (FolderSchema, ImapAccount, MailbotMode, MessageSchema, EmailRule)
from datetime import datetime, timedelta
from browser.imap import *
from imapclient import IMAPClient
from engine.constants import *
from engine.youps import login_imap
from smtp_handler.Pile import *
import datetime
from http_handler.settings import WEBSITE, TEST_ACCOUNT_EMAIL, TEST_ACCOUNT_PASSWORD
from browser.sandbox import interpret_bypass_queue 
from engine.models.mailbox import MailBox  # noqa: F401 ignore unused we use it for typing
from smtp_handler.utils import send_email

logger = logging.getLogger('youps')  # type: logging.Logger

class Command(BaseCommand):
    args = ''
    help = 'Process email'

    # Auto-send messages to TEST_ACCOUNT_EMAIL and see the results match expected results by running multiple unit tests
    def handle(self, *args, **options):
        if len(args) == 0:
            print ("option: send-test|run-test")
            print ("You should run `send-test` at least once prior to `run-test`")
            return

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
                    'body_plain': '😎',
                    'body_html': '😎'
                },
            ]

        if args[0] == "send-test":
            index = 0
            for t in test_emails:
            #     # TODO send using django core
            #     send_mail("#%d " % index + t['subject'].decode('utf-8'), t['body_plain'], TEST_ACCOUNT_EMAIL, [TEST_ACCOUNT_EMAIL])
                send_email("#%d " % index + t['subject'].decode('utf-8'), t['from_addr'], TEST_ACCOUNT_EMAIL, t['body_plain'].decode('utf-8'), t['body_html'].decode('utf-8'))
                index = index + 1

        elif args[0] == "run-test":
            imapAccount = None
            imap = None

            # Auth to test email accountss
            try:
                imapAccount = ImapAccount.objects.get(email=TEST_ACCOUNT_EMAIL)
            except ImapAccount.DoesNotExist:
                login_imap(TEST_ACCOUNT_EMAIL, TEST_ACCOUNT_PASSWORD, 'imap.gmail.com',is_oauth=False)

                print("Just created a YouPS account for a test account. It will take couple minutes to set up")
                return

            try:
                auth_res = authenticate( imapAccount )
                if not auth_res['status']:
                    raise ValueError('Something went wrong during authentication. Refresh and try again!')

                imap = auth_res['imap']  # noqa: F841 ignore unused
            except Exception, e:
                print("failed logging into imap", str(e))
                return

            test_cases = [
                [ # test cases for #0 email
                    {
                        'code': 'print (my_message.from_)',
                        'expected': 'test@youps.csail.mit.edu'
                    }, 
                    {
                        'code': 'print("True" if "test@youps.csail.mit.edu" == my_message.from_ else "") ',
                        'expected': 'test@youps.csail.mit.edu'
                    }, 
                    {
                        'code': 'print("True" if "test email " in my_message.subject else "") ',
                        'expected': 'True'
                    }, 
                    {
                        'code': 'send(subject="hello", to="soyapark2535@gmail.com")',
                        'expected': 'True'
                    }, 
                ],
                [
                    {
                        'code': 'print ("True" if "🤷‍♀️" in my_message.subject else "")',
                        'expected': 'True'
                    },
                    {
                        'code': 'print ("True" if my_message.contains("😎") else "")',
                        'expected': 'True'
                    },
                ]
            ]            
            
            # Run test
            try:
                folder_names = ["INBOX"]
                for msg_index in range(len(test_cases)):
                    for folder_name in folder_names:
                        # pick up recent messages 
                        message = MessageSchema.objects.filter( \
                            imap_account=imapAccount, folder__name=folder_name, base_message__subject__startswith='#%d ' % msg_index).order_by("-base_message__date")

                        if not message.exists():
                            print ("Unable to load the corresponding message #%d %s" % (msg_index, test_emails[msg_index]['subject']))
                            continue

                        message = message[0]
                        assert isinstance(message, MessageSchema)

                        mailbox = MailBox(imapAccount, imap, is_simulate=True)
                        for test_per_message_index in range(len(test_cases[msg_index])):
                            imap_res = interpret_bypass_queue(mailbox, extra_info={'code': "def on_message(my_message):\n\t" + \
                                test_cases[msg_index][test_per_message_index]['code'].decode("utf-8", "replace"), 'msg-id': message.id})
                            # print(imap_res)

                            try:
                                assert imap_res['appended_log'][message.id]['log'].rstrip("\n\r") == test_cases[msg_index][test_per_message_index]['expected']
                            except AssertionError:
                                print ("CASE #%d-%d %s (expected %s)" % (msg_index, test_per_message_index, \
                                    imap_res['appended_log'][message.id]['log'].rstrip("\n\r"), test_cases[msg_index][test_per_message_index]['expected']))
                                continue

                            print ("SUCCESS #%d-%d %s" % (msg_index, test_per_message_index, test_emails[msg_index]['subject']))
            except Exception, e:
                print("failed while doing a user code run %s %s " % (e, traceback.format_exc()))
            finally:
                imap.logout()