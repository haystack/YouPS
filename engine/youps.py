import base64
import logging
import random
import string
import traceback
import datetime

from Crypto.Cipher import AES
from imapclient import IMAPClient

from browser.imap import GoogleOauth2, authenticate
from engine.models.mailbox import MailBox
from browser.sandbox import interpret
from engine.constants import msg_code
from http_handler.settings import IMAP_SECRET
from schema.youps import (FolderSchema, ImapAccount, MailbotMode, MessageSchema, EmailRule)
from engine.models.message import Message  # noqa: F401 ignore unused we use it for typing
import typing as t

logger = logging.getLogger('youps')  # type: logging.Logger

def login_imap(email, password, host, is_oauth):
    """This function is called only once per each user when they first attempt to login to YoUPS.
    check if we are able to login to the user's imap using given credientials.
    if we can, encrypt and store credientials on our DB. 

        Args:
            email (string): user's email address
            password (string): if is_oauth True, then it contains oauth token. Otherwise, it is plain password
            host (string): IMAP host address
            is_oauth (boolean): if the user is using oauth or not
    """

    logger.info('adding new account %s' % email)
    res = {'status' : False}

    try:
        imap = IMAPClient(host, use_uid=True)

        refresh_token = ''
        access_token = ''
        if is_oauth:
            # TODO If this imap account is already mapped with this account, bypass the login.
            oauth = GoogleOauth2()
            response = oauth.generate_oauth2_token(password)
            refresh_token = response['refresh_token']
            access_token = response['access_token']

            imap.oauth2_login(email, access_token)

        else:
            imap.login(email, password)

            # encrypt password then save
            aes = AES.new(IMAP_SECRET, AES.MODE_CBC, 'This is an IV456')

            # padding password
            padding = random.choice(string.letters)
            while padding == password[-1]:
                padding = random.choice(string.letters)
                continue
            extra = len(password) % 16
            if extra > 0:
                password = password + (padding * (16 - extra))
            password = aes.encrypt(password)

        imapAccount = ImapAccount.objects.filter(email=email)
        if not imapAccount.exists():
            imapAccount = ImapAccount(email=email, password=base64.b64encode(password), host=host)
            imapAccount.host = host

            # = imapAccount
        else:
            imapAccount = imapAccount[0]
            imapAccount.password = base64.b64encode(password)
            res['imap_code'] = ""  # TODO PLEASE REMOVE THIS WOW
            res['imap_log'] = imapAccount.execution_log


        if is_oauth:
            imapAccount.is_oauth = is_oauth
            imapAccount.access_token = access_token
            imapAccount.refresh_token = refresh_token

        imapAccount.is_gmail = imap.has_capability('X-GM-EXT-1')

        imapAccount.save()

        res['status'] = True
        logger.info("added new account %s" % imapAccount.email)

    except IMAPClient.Error, e:
        res['code'] = e
    except Exception, e:
        logger.exception("Error while login %s %s " % (e, traceback.format_exc()))
        res['code'] = msg_code['UNKNOWN_ERROR']

    return res

def fetch_execution_log(user, email, push=True):
    res = {'status' : False}

    try:
        imapAccount = ImapAccount.objects.get(email=email)
        res['imap_log'] = imapAccount.execution_log
        res['user_status_msg'] = imapAccount.status_msg
        res['status'] = True

    except ImapAccount.DoesNotExist:
        res['code'] = "Error during authentication. Please refresh"
    except Exception, e:
        # TODO add exception
        print e
        res['code'] = msg_code['UNKNOWN_ERROR']

    logging.debug(res)
    return res

def delete_mailbot_mode(user, email, mode_id, push=True):
    res = {'status' : False}

    try:
        imapAccount = ImapAccount.objects.get(email=email)
        mm = MailbotMode.objects.get(uid=mode_id, imap_account=imapAccount)

        if imapAccount.current_mode == mm:
            imapAccount.current_mode = None
            imapAccount.is_running = False

        mm.delete()

        res['status'] = True

    except ImapAccount.DoesNotExist:
        res['code'] = "Error during deleting the mode. Please refresh the page."
    except MailbotMode.DoesNotExist:
        res['code'] = "Error during deleting the mode. Please refresh the page."
    except Exception, e:
        # TODO add exception
        print e
        res['code'] = msg_code['UNKNOWN_ERROR']

    logging.debug(res)
    return res

def remove_rule(user, email, rule_id):
    """This function remove a EmailRule of user;

        Args:
            user (Model.UserProfile)
            email (string): user's email address
            rule_id (integer): ID of EmailRule to be deleted
    """
    res = {'status' : False, 'imap_error': False}

    try:
        imap_account = ImapAccount.objects.get(email=email)
        er = EmailRule.objects.filter(uid=rule_id, mode__imap_account=imap_account)

        er.delete()

        res['status'] = True
    except IMAPClient.Error, e:
        res['code'] = e
    except ImapAccount.DoesNotExist:
        res['code'] = "Not logged into IMAP"
    except Exception, e:
        # TODO add exception
        print e
        res['code'] = msg_code['UNKNOWN_ERROR']

    logging.debug(res)
    return res

def run_mailbot(user, email, current_mode_id, modes, is_test, run_request, push=True):
    """This function is called everytime users hit "run", "stop" or "save" their scripts.

        Args:
            user (Model.UserProfile)
            email (string): user's email address
            current_mode_id (integer): ID of currently selected/running mode
            modes (list): a list of dicts that each element is information about each user's mode
            is_test (boolean): if is_test is True, then it just simulates the user's script and prints out log but not actually execute it.  
            run_request (boolean): if False, set the current_mode to None so the event is not fired at interpret()
    """
    res = {'status' : False, 'imap_error': False, 'imap_log': ""}
    logger = logging.getLogger('youps')  # type: logging.Logger

    # this log is going to stdout but not going to the logging file
    # why are django settings not being picked up
    logger.info("user %s has run, stop, or saved" % email)

    imap = None

    try:
        imapAccount = ImapAccount.objects.get(email=email)
        auth_res = authenticate( imapAccount )
        if not auth_res['status']:
            raise ValueError('Something went wrong during authentication. Refresh and try again!')

        imap = auth_res['imap']  # noqa: F841 ignore unused

        imapAccount.is_test = is_test
        imapAccount.is_running = run_request

        # TODO these don't work anymore
        # uid = fetch_latest_email_id(imapAccount, imap)
        # imapAccount.newest_msg_id = uid

        # remove all user's tasks of this user to keep tasks up-to-date

        for mode_index, mode in modes.iteritems():
            mode_id = mode['id']
            mode_name = mode['name'].encode('utf-8')
            mode_name = mode_name.split("<br>")[0] if mode_name else "mode"
            logger.info(mode_name)
            mailbotMode = MailbotMode.objects.filter(uid=mode_id, imap_account=imapAccount)
            if not mailbotMode.exists():
                mailbotMode = MailbotMode(uid=mode_id, name=mode_name, imap_account=imapAccount)
                

            else:
                mailbotMode = mailbotMode[0]
                mailbotMode.name = mode_name

            mailbotMode.save()

            # Remove old editors to re-save it
            # TODO  dont remove it
            er = EmailRule.objects.filter(mode=mailbotMode)
            logger.debug("deleting er editor run request")
            er.delete()

            for value in mode['editors']:
                uid = value['uid']
                name = value['name'].encode('utf-8')

                logger.critical('uid: {uid} name: {name}'.format(uid=uid, name=name))

            for value in mode['editors']:
                uid = value['uid']
                name = value['name'].encode('utf-8')
                code = value['code'].encode('utf-8')
                folders = value['folders']
                logger.info("saving editor %s run request" % uid)
                
                er = EmailRule(uid=uid, name=name, mode=mailbotMode, type=value['type'], code=code)
                er.save()

                logger.info("user %s test run " % imapAccount.email)

                # res = interpret(MailBox(imapAccount, imap), None, True, {'code' : code})
                # logger.critical(res["appended_log"])

                # # Save selected folder for the mode
                for f in folders:
                    folder = FolderSchema.objects.get(imap_account=imapAccount, name=f)
                    logger.info("saving folder to the editor %s run request" % folder.name)
                    er.folders.add(folder)

                er.save()

        

        if run_request:
            imapAccount.current_mode = MailbotMode.objects.filter(uid=current_mode_id, imap_account=imapAccount)[0]

            # if the code execute well without any bug, then save the code to DB
            if not res['imap_error']:
                pass
        else:
            imapAccount.current_mode = None

        imapAccount.save()

        # res['imap_log'] = ("[TEST MODE] Your rule is successfully installed. It won't take actual action but simulate your rule. %s \n" + res['imap_log']) if is_test else ("Your rule is successfully installed. \n" + res['imap_log'])
        #         now = datetime.now()
        #         now_format = now.strftime("%m/%d/%Y %H:%M:%S") + " "
        #         res['imap_log'] = now_format + res['imap_log']
        #     else:
        #         imapAccount.is_running = False
        #         imapAccount.save()
        # else:

        #     res['imap_log'] = "Your mailbot stops running"
        

        res['status'] = True

    except IMAPClient.Error, e:
        logger.exception("failed while doing a user code run")
        res['code'] = e
    except ImapAccount.DoesNotExist:
        logger.exception("failed while doing a user code run")
        res['code'] = "Not logged into IMAP"
    except FolderSchema.DoesNotExist:
        logger.exception("failed while doing a user code run")
        logger.debug("Folder is not found, but it should exist!")
    except Exception, e:
        # TODO add exception
        logger.exception("failed while doing a user code run")
        print e
        print (traceback.format_exc())
        res['code'] = msg_code['UNKNOWN_ERROR']
    finally:
        imap.logout()

    logging.debug(res)
    return res

def run_simulate_on_messages(user, email, folder_names, N=3, code=''):
    """This function is called to evaluate user's code on messages

        Args:
            user (Model.UserProfile)
            email (string): user's email address
            folder_name (string): name of a folder to extract messages 
            N (int): number of recent messages
            code (string): code to be simulated
    """
    res = {'status' : False, 'imap_error': False, 'imap_log': ""}
    logger = logging.getLogger('youps')  # type: logging.Logger

    # this log is going to stdout but not going to the logging file
    # why are django settings not being picked up
    logger.info("user %s has requested simulation" % email)

    imapAccount = None
    imap = None

    try:
        imapAccount = ImapAccount.objects.get(email=email)
        auth_res = authenticate( imapAccount )
        if not auth_res['status']:
            raise ValueError('Something went wrong during authentication. Refresh and try again!')

        imap = auth_res['imap']  # noqa: F841 ignore unused
    except Exception, e:
        logger.exception("failed while logging into imap")
        res['code'] = "Fail to access your IMAP account"
        return

    try:
        res['messages'] = {}

        for folder_name in folder_names:
            messages = MessageSchema.objects.filter(imap_account=imapAccount, folder__name=folder_name).order_by("-base_message__date")[:N]

            for message_schema in messages:
                assert isinstance(message_schema, MessageSchema)
                imap_res = interpret(MailBox(imapAccount, imap), None, bypass_queue=True, is_simulate=True, extra_info={'code': code, 'msg-id': message_schema.id})
                logger.info(imap_res)

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

    logging.debug(res)
    return res

def save_shortcut(user, email, shortcuts, push=True):
    res = {'status' : False, 'imap_error': False}

    try:
        imapAccount = ImapAccount.objects.get(email=email)

        imapAccount.shortcuts = shortcuts
        imapAccount.save()

        res['status'] = True


    except IMAPClient.Error, e:
        res['code'] = e
    except ImapAccount.DoesNotExist:
        res['code'] = "Not logged into IMAP"
    except Exception, e:
        # TODO add exception
        print e
        res['code'] = msg_code['UNKNOWN_ERROR']

    logging.debug(res)
    return res