import sys
import base64
import logging
import random
import string
import traceback
import datetime
import dateutil.parser
import json
import requests
from time import sleep
from itertools import chain

from Crypto.Cipher import AES
from imapclient import IMAPClient, exceptions

from django.utils import timezone
from pytz import timezone as tz
from browser.imap import GoogleOauth2, authenticate
from engine.models.mailbox import MailBox
from browser.sandbox import interpret_bypass_queue 
from engine.constants import msg_code
from engine.utils import get_calendar_range, turn_on_youps, prettyPrintTimezone, print_execution_log
from http_handler.settings import IMAP_SECRET
from schema.youps import (FolderSchema, ImapAccount, MailbotMode, ContactSchema, MessageSchema, EmailRule, EmailRule_Args, ButtonChannel, LogSchema)
from engine.models.message import Message, Contact  # noqa: F401 ignore unused we use it for typing

from http_handler.settings import NYLAS_ID, NYLAS_SECRET
from nylas import APIClient
from engine.utils import auth_to_nylas

logger = logging.getLogger('youps')  # type: logging.Logger
button_logger = logging.getLogger('button') # type: logging.Logger

def login_imap(email, username, password, host, is_oauth):
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
            imap.login(username, password)

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
            imapAccount = ImapAccount(email=email, username=username, password=base64.b64encode(password), host=host)
            imapAccount.host = host

            # = imapAccount
        else:
            imapAccount = imapAccount[0]
            imapAccount.password = base64.b64encode(password)
            res['imap_code'] = ""  # TODO PLEASE REMOVE THIS WOW
            res['imap_log'] = ""


        if is_oauth:
            imapAccount.is_oauth = is_oauth
            imapAccount.access_token = access_token
            imapAccount.refresh_token = refresh_token

        imapAccount.is_gmail = imap.has_capability('X-GM-EXT-1')

        imapAccount.save()

        res['status'] = True
        logger.info("added new account %s" % imapAccount.email)

    except exceptions.LoginError:
        res['code'] = "Wrong username or password"
    except IMAPClient.Error as e:
        res['code'] = e
        logger.exception(e)
    except Exception as e:
        logger.exception("Error while login %s %s " % (e, traceback.format_exc()))
        res['code'] = msg_code['UNKNOWN_ERROR']

    return res

def fetch_execution_log(user, email, from_id=None, to_id=None, push=True):
    res = {'status' : False}

    try:
        imapAccount = ImapAccount.objects.get(email=email)
        d = {}
        if from_id is None and to_id is None: # return first 10 
            logs = LogSchema.objects.filter(imap_account=imapAccount, is_canceled=False).order_by("-timestamp")[:10]
                
        elif from_id is None:
            logs = LogSchema.objects.filter(id__lte=to_id, is_canceled=False).filter(imap_account=imapAccount)

        elif to_id is None:
            logs = LogSchema.objects.filter(id__gte=from_id, is_canceled=False).filter(imap_account=imapAccount)
        
        else:    
            logs = LogSchema.objects.filter(id__range=[from_id, to_id], is_canceled=False).filter(imap_account=imapAccount)

        for l in logs:
            # logger.exception(l.content)
            # TODO get keys in the tmp then add logschema_id
            tmp = json.loads(l.content)
            k = tmp.keys()[0]
            tmp[k]["property_log"] = l.action
            tmp[k]["logschema_id"] = l.id
            d.update( tmp )

        res["log_min_id"] = -1
        res["log_max_id"] = -1
        if logs.exists():
            ids = list(logs.values_list('id', flat=True))
            res["log_min_id"] = ids[-1] # queryset is descending 
            res["log_max_id"] = ids[0]

        res['imap_log'] = json.dumps(d)
        res['user_status_msg'] = imapAccount.status_msg
        res['status'] = True

    except ImapAccount.DoesNotExist:
        res['code'] = "Please log in to your email account first"
        res['imap_authenticated'] = False
    except Exception as e:
        # TODO add exception
        logger.exception(e)
        res['code'] = msg_code['UNKNOWN_ERROR']

    return res

def apply_button_rule(user, email, er_id, msg_schema_id, kargs):
	res = {'status' : False}
	
	try:
		imapAccount = ImapAccount.objects.get(email=email)
		auth_res = authenticate( imapAccount )
		if not auth_res['status']:
		    raise ValueError('Something went wrong during authentication. Refresh and try again!')

		imap = auth_res['imap']  # noqa: F841 ignore unused

		er = EmailRule.objects.get(id=er_id)
        #  read from DB and convert to the type accordingly 
		for key, value in kargs.iteritems():
		    er_arg = EmailRule_Args.objects.get(rule=er, name=key)

            # parse datetime 
		    if er_arg.type == "datetime":
		        try: 
		            kargs[key] = datetime.datetime.strptime(value, '%Y-%m-%d %H:%M')
		        except Exception:
		            res['code'] = key
		            logger.info("qwersdf")
		            raise TypeError

		mailbox = MailBox(imapAccount, imap, is_simulate=False)
		res = interpret_bypass_queue(mailbox, extra_info={"msg-id": msg_schema_id, "code": er.code, "shortcut": kargs, "rule_name": er.name})
		logger.info(kargs) 
		logger.debug(er.code)
		# logger.info(res)
		res['status'] = True
	
	except ImapAccount.DoesNotExist:
	    res['code'] = "Error during deleting the mode. Please refresh the page."
	except MailbotMode.DoesNotExist:
	    res['code'] = "Error during deleting the mode. Please refresh the page."
	except TypeError as e:
	    res['code'] = "Datetime %s is in wrong format!" % e
	except Exception as e:
	    logger.exception(e)
	    res['code'] = msg_code['UNKNOWN_ERROR']
	return res
    
def remove_on_response_event(user, email, msg_schema_id):
    res = {'status' : False}
    
    try:
		imapAccount = ImapAccount.objects.get(email=email)


		msg = MessageSchema.objects.get(id=msg_schema_id)
		msg.base_message._thread.events.clear()

		# logger.info(res)
		res['status'] = True	    
    except ImapAccount.DoesNotExist:
	    res['code'] = "Error during deleting the mode. Please refresh the page."
    except TypeError as e:
	    res['code'] = "Datetime %s is in wrong format!" % e
    except Exception as e:
	    logger.exception(e)
	    res['code'] = msg_code['UNKNOWN_ERROR']
    return res

def remove_on_time_event(user, email, msg_schema_id):
    res = {'status' : False}
    
    try:
		imapAccount = ImapAccount.objects.get(email=email)

		msg = MessageSchema.objects.get(id=msg_schema_id)
		msg.base_message.events.clear()

		# logger.info(res)
		res['status'] = True	    
    except ImapAccount.DoesNotExist:
	    res['code'] = "Error during deleting the mode. Please refresh the page."
    except TypeError as e:
	    res['code'] = "Datetime %s is in wrong format!" % e
    except Exception as e:
	    logger.exception(e)
	    res['code'] = msg_code['UNKNOWN_ERROR']
    return res

def create_mailbot_mode(user, email, push=True):
	res = {'status' : False}
	
	try:
	    imapAccount = ImapAccount.objects.get(email=email)
	    mm = MailbotMode(imap_account=imapAccount, name="My Email Mode")
	    mm.save()
	
	    res["mode-id"] = mm.id
	    res['status'] = True
	
	except ImapAccount.DoesNotExist:
	    res['code'] = "Error during deleting the mode. Please refresh the page."
	except MailbotMode.DoesNotExist:
	    res['code'] = "Error during deleting the mode. Please refresh the page."
	except Exception as e:
	    logger.exception(res)
	    res['code'] = msg_code['UNKNOWN_ERROR']
	return res

def delete_mailbot_mode(user, email, mode_id, push=True):
    res = {'status' : False}
    
    try:
        imapAccount = ImapAccount.objects.get(email=email)
        mm = MailbotMode.objects.get(id=mode_id, imap_account=imapAccount)
        if imapAccount.current_mode == mm:
            turn_on_youps(imapAccount, False, "by delete_mailbot_mode")
            imapAccount.current_mode = None
            imapAccount.save()
        mm.delete()
        res['status'] = True
    except ImapAccount.DoesNotExist:
        res['code'] = "Error during deleting the mode. Please refresh the page."
    except MailbotMode.DoesNotExist:
        res['code'] = "Error during deleting the mode. Please refresh the page."
    except Exception as e:
        logger.exception(res)
        res['code'] = msg_code['UNKNOWN_ERROR']
    
    return res


def fetch_watch_message(user, email, watched_message):
    res = {'status' : False, 'log': "", 'messages': {}}

    try:
        imapAccount = ImapAccount.objects.get(email=email)
        res['watch_status'] = True
    except ImapAccount.DoesNotExist:
        res['code'] = "Error during authentication. Please refresh"
        return
    
    try: 
        imap = None

        auth_res = authenticate( imapAccount )
        if not auth_res['status']:
            raise ValueError('Something went wrong during authentication. Refresh and try again!')

        imap = auth_res['imap']  # noqa: F841 ignore unused
    except Exception as e:
        logger.exception("failed while logging into imap")
        res['code'] = "Fail to access your IMAP account"
        return res

    try:
        if res['watch_status']:
            imapAccount.sync_paused = True
            mailbox = MailBox(imapAccount, imap, is_simulate=False)
            msgs = None
            cnt = 0 
            while True:
                for folder in mailbox._list_selectable_folders():
                    response = imap.select_folder(folder.name)

                    highest_mod_seq = response.get('HIGHESTMODSEQ')
                    logger.debug(highest_mod_seq)

                    # this mailbox is using highest mod_seq and there is no update  
                    if highest_mod_seq is not None and folder._highest_mod_seq <= 0:
                        continue

                    # logger.info("refresh flags")
                    # logger.critical(folder.name)
                    msgs = folder._refresh_flag_changes(highest_mod_seq)

                    if msgs:
                        res['contexts'] = []
                        for r in msgs:

                            # if this message is already caught, skip to next to find another new msgs
                            logger.debug(r.id)
                            logger.debug(watched_message)
                            if str(r.base_message.id) in watched_message:
                                continue
                            logger.info(r.base_message.subject)
                            message = Message(r, imap_client=imap)   
                            res['message'] = message._get_meta_data_friendly()
                            res['sender'] = message._get_from_friendly()
                            
                            try:
                                message_arrival_time = dateutil.parser.parse(res["message"]["date"])
                                # if the message arrives today, send only hour and minute
                                if message_arrival_time.date() == datetime.datetime.today().date():
                                    res["message"]["date"] = "%d:%02d" % (message_arrival_time.hour, message_arrival_time.minute)
                            except:
                                logger.exception("parsing arrival date fail; skipping parsing")

                            on_time = False
                            on_response = False
                            if r.base_message._thread:
                                if r.base_message._thread.events.all():
                                    on_response = True
                            
                            if r.base_message.events.all():
                                on_time = True
                                

                            # 'message_events': r.base_message.events, 
                            # Contact(contact_schema, self._imap_client, self._is_simulate) for contact_schema in self._schema.base_message.to.all()
                            res['contexts'].append( {'on_time': int(on_time), "on_response": int(on_response),'base_message_id': r.base_message.id,'sender': res['sender']["name"] or res['sender']["email"], "subject": res['message']['subject'], "date": res["message"]["date"], "message_id": r.id} )

                        # if there is update, send it to the client immediatly 
                        if 'message' in res:
                            res['status'] = True
                            return res

                # r=requests.get(url, headers=headers)

                # if r.json()['deltas']:
                #     break
                # # logger.info("finding delta..")
                if cnt == 10:
                    break
                cnt = cnt +1
                sleep(0.01)

            # for d in r.json()['deltas']:
            #     if d['object'] == "message" or d['object'] == "thread":
            #         logger.info(d['attributes']['subject'])
            #         res["log"] = d['attributes']['subject']

            # if bc and bc.code == ButtonChannel.OK:
            #     res['folder'] = bc.message.folder.name
            #     res['uid'] = bc.message.id 
                
            #     message = Message(bc.message, imap_client="")   # since we are only extracting metadata, no need to use imap_client
            #     res['message'] = message._get_meta_data_friendly() 
            #     res['sender'] = message._get_from_friendly()
            # else:
            #     # if something went wrong only return the log
            #     logger.info(bc.code)
            #     res["log"] = "%s - %s" % (bc.get_code_display(), bc.log)
        
        res['status'] = True

    except ButtonChannel.DoesNotExist:
        res['uid'] = 0
    except Exception as e:
        logger.exception(e)
        res['code'] = msg_code['UNKNOWN_ERROR']
    finally:
        logger.info("Finish watching cycle")
        imapAccount.sync_paused = False
        imap.logout()

    return res

def fetch_upcoming_events(user, email):
    res = {'status' : False, "events": []}

    try:
        imapAccount = ImapAccount.objects.get(email=email)


        res["events"] = get_calendar_range(imapAccount, start=datetime.datetime.now())

        res['status'] = True

    except ImapAccount.DoesNotExist:
        res['code'] = "Error during authentication. Please refresh"
    except Exception as e:
        logger.exception(e)
        res['code'] = msg_code['UNKNOWN_ERROR']
    return res


def fetch_available_email_rule(user, email):
    res = {'status' : False}

    try:
        imapAccount = ImapAccount.objects.get(email=email)

        # list available rules 
        # Send name of emailrule and its args 
        ers = EmailRule.objects.filter(mode__imap_account=imapAccount, type__startswith='new-message')

        res['status'] = True

    except ImapAccount.DoesNotExist:
        res['code'] = "Error during authentication. Please refresh"
    except Exception as e:
        logger.exception(e)
        res['code'] = msg_code['UNKNOWN_ERROR']
    return res

def get_deltas_cursors(user, email):
    res = {'status' : False, 'log': "", "cursor": ""}

    try:
        imapAccount = ImapAccount.objects.get(email=email)
        res['watch_status'] = True
        url = 'https://api.nylas.com/delta/latest_cursor'
        user_access_token = 'xx'
        headers = {'Authorization': user_access_token, 'Content-Type': 'application/json', 'cache-control': 'no-cache'}
        r=requests.post(url, headers=headers)

        res['cursor'] = r.json()['cursor']

        res['status'] = True

    except ImapAccount.DoesNotExist:
        res['code'] = "Error during authentication. Please refresh"
    except Exception as e:
        logger.exception(e)
        res['code'] = msg_code['UNKNOWN_ERROR']

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
        er = EmailRule.objects.filter(id=rule_id)

        er.delete()

        res['status'] = True
    except IMAPClient.Error as e:
        res['code'] = e
    except ImapAccount.DoesNotExist:
        res['code'] = "Not logged into IMAP"
    except Exception as e:
        res['code'] = msg_code['UNKNOWN_ERROR']

    logging.debug(res)
    return res

def save_rules(user, email, old_ers, rules, mailbotMode=None, push=True):
    res = {'status' : False, 'imap_error': False, 'imap_log': ""}

    try:
        imapAccount = ImapAccount.objects.get(email=email)
        auth_res = authenticate( imapAccount )
        if not auth_res['status']:
            raise ValueError('Something went wrong during authentication. Refresh and try again!')

        imap = auth_res['imap']  # noqa: F841 ignore unused

        mailbox = MailBox(imapAccount, imap, is_simulate=False)
        # Remove old editors to re-save it
        # TODO  dont remove it
        
        for er in old_ers:
            # update contact for email triggering
            # delete old name 
            mailbox._delete_contact(er.get_forward_addr())

        logger.debug("deleting er editor run request")
        
        args = EmailRule_Args.objects.filter(rule=old_ers)
        args.delete()
        old_ers.delete()

        for value in rules:
            name = value['name'].encode('utf-8')
            code = value['code'].encode('utf-8')
            # code = code.replace("\xa0", " ")
            # logger.info(code.split("\n"))
            
            folders = value['folders']
            logger.info(mailbotMode)
            er = None

            if mailbotMode:
                er = EmailRule(name=name, mode=mailbotMode, type=value['type'], code=code)
            else:
                er = EmailRule(name=name, imap_account=imapAccount, type=value['type'], code=code)
            er.save()

            # Save selected folder for the mode
            for f in folders:
                folder = FolderSchema.objects.get(imap_account=imapAccount, name=f)
                logger.info("saving folder to the editor %s run request" % folder.name)
                er.folders.add(folder)

            er.save()

            if value['type'] == "shortcut":
                # Save shortcut email args
                for arg in value['args']:
                    logger.info(arg)
                    
                    new_arg = EmailRule_Args(type=arg['type'], rule=er)
                    if arg['name']:
                        new_arg.name = arg['name']
                    new_arg.save()

                # add a new contact
                logger.info("add contact %s" % er.get_forward_addr())
                mailbox._add_contact("YouPS", er.get_forward_addr())

        res['status'] = True

    except Exception as e:
        # TODO add exception
        logger.exception("failed while doing a user code run")
        print (traceback.format_exc())
        res['code'] = msg_code['UNKNOWN_ERROR']

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
        turn_on_youps(imapAccount, run_request, "By user's request")


        # remove all user's tasks of this user to keep tasks up-to-date
        # old_mailbotMode = MailbotMode.objects.filter(imap_account=imapAccount)
        # old_mailbotMode.delete()

        for mode_index, mode in modes.iteritems():
            mode_name = mode['name'].encode('utf-8')
            mode_name = mode_name.split("<br>")[0] if mode_name else "mode"
            logger.info(mode_name)
            
            mailbotMode = MailbotMode.objects.filter(id=mode['id'], imap_account=imapAccount)
            if mailbotMode.exists():
                mailbotMode = mailbotMode[0]
                # logger.info(mailbotMode.values())
                mailbotMode.name = mode_name
                mailbotMode.save()
            else:
                mailbotMode = MailbotMode(name=mode_name, imap_account=imapAccount)
                mailbotMode.save()

           
            ers = EmailRule.objects.filter(mode=mailbotMode)

            r = save_rules(user, email, ers, mode['editors'], mailbotMode)
            
            logger.info(MailbotMode.objects.filter(imap_account=imapAccount).values('name', 'id'))
            logger.info(EmailRule.objects.filter(mode=mailbotMode).values('name', 'id'))
        

        if run_request:
            logger.info(current_mode_id)
            imapAccount.current_mode = MailbotMode.objects.get(id=current_mode_id, imap_account=imapAccount)

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

    except IMAPClient.Error as e:
        logger.exception("failed while doing a user code run")
        res['code'] = e
    except ImapAccount.DoesNotExist:
        logger.exception("failed while doing a user code run")
        res['code'] = "Not logged into IMAP"
    except FolderSchema.DoesNotExist:
        logger.exception("failed while doing a user code run")
        logger.debug("Folder is not found, but it should exist!")
    except MailbotMode.DoesNotExist:
        logger.exception("No current mode exist")
        res['code'] = "Currently no mode is selected. Select one of your mode to execute your YouPS."
    except ValueError:
        logger.exception("login error")
        res['code'] = 'Something went wrong during authentication. If this persists, contact our team!'
    except Exception as e:
        # TODO add exception
        logger.exception("failed while doing a user code run")
        print (traceback.format_exc())
        res['code'] = msg_code['UNKNOWN_ERROR']
    finally:
        if imap:
            imap.logout()

    logging.debug(res)
    return res

def run_simulate_on_messages(user, email, folder_names, N=3, code='', extra_info={}):
    """This function is called to evaluate user's code on messages

        Args:
            user (Model.UserProfile)
            email (string): user's email address
            folder_name (string): name of a folder to extract messages 
            N (int): number of recent messages
            code (string): code to be simulated
            extra_info (list): a list of dictionary contains extra information such as argument list for shortucts
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
    except Exception as e:
        logger.exception("failed while logging into imap")
        res['code'] = "Fail to access your IMAP account"
        return res

    try:
        res['messages'] = {}
        
        args = {}
        messages = None
        for e in extra_info:
            if "type" in e:
                args[e["name"]] = datetime.datetime.now() if e["type"] == "datetime" else "test string"
            elif "messageschema-id" in e:
                msgs = MessageSchema.objects.filter(imap_account=imapAccount, id=e["messageschema-id"])
                messages = list(chain(messages, msgs)) if messages else msgs

        for folder_name in folder_names:
            msgs = MessageSchema.objects.filter(imap_account=imapAccount, folder__name=folder_name).order_by("-base_message__date")[:N]
            messages = list(chain(messages, msgs)) if messages else msgs

        for message_schema in messages:
            assert isinstance(message_schema, MessageSchema)
            mailbox = MailBox(imapAccount, imap, is_simulate=True)
            imap_res = interpret_bypass_queue(mailbox, extra_info={'code': code, 'msg-id': message_schema.id, 'shortcut':args})
            logger.debug(imap_res)

            message = Message(message_schema, imap)
            result = print_execution_log(message)
            result["property_log"] = imap_res['appended_log'][message_schema.id]['property_log']
            result["log"] = imap_res['appended_log'][message_schema.id]['log']
            result["error"] = imap_res['appended_log'][message_schema.id]['error'] if 'error' in imap_res['appended_log'][message_schema.id] else False

            res['messages'][message_schema.id] = result
                
        
        res['status'] = True
    except ImapAccount.DoesNotExist:
        logger.exception("failed while doing a user code run")
        res['code'] = "Not logged into IMAP"
    except FolderSchema.DoesNotExist:
        logger.exception("failed while doing a user code run")
        logger.debug("Folder is not found, but it should exist!")
    except Exception as e:
        logger.exception("failed while doing a user code run %s %s " % (e, traceback.format_exc()))
        res['code'] = msg_code['UNKNOWN_ERROR']
    finally:
        imap.logout()

    logging.debug(res)
    return res


def undo(user, email, logschema_id):
    res = {'status' : False, 'log': ""}

    try:
        imapAccount = ImapAccount.objects.get(email=email)
        logschema = LogSchema.objects.get(id=logschema_id)

        actions = json.loads(logschema.action)
    
        auth_res = authenticate( imapAccount )
        if not auth_res['status']:
            raise ValueError('Something went wrong during authentication. Refresh and try again!')

        imap = auth_res['imap']  # noqa: F841 ignore unused
    except ImapAccount.DoesNotExist:
        res['code'] = "Not logged into IMAP"
    except LogSchema.DoesNotExist:
        res['code'] = "Can't undo the action!"
    except Exception as e:
        logger.exception("failed while logging into imap")
        res['code'] = "Fail to access your IMAP account"
        return res

    try:
        # Redo actions reverse to undo
        logger.critical(actions)
        for action in reversed(actions):
            target_class = None
            if action["class_name"] == "Message":
                if action["function_name"] == "_move":
                    logger.info("folder %s" % action["args"][1])
                    message_schema = MessageSchema.objects.filter(base_message__id=action["schema_id"], folder__name=action["args"][1])
                    #target_class._imap_client.select_folder(target_class.folder.name)
                else:
                    message_schema = MessageSchema.objects.filter(base_message__id=action["schema_id"])

                logger.critical(action["schema_id"])
                if not message_schema.exists():
                    raise MessageSchema.DoesNotExist

                message_schema = message_schema[0]
                target_class = Message(message_schema, imap_client=imap)
            elif action["class_name"] == "Contact":
                contact_schema = ContactSchema.objects.filter(id=action["schema_id"])
                logger.critical(action["schema_id"])
                if not contact_schema.exists():
                    raise ContactSchema.DoesNotExist

                contact_schema = contact_schema[0]
                target_class = Contact(contact_schema, imap_client=imap)

            if action["type"] == "send":
                logger.info("unreversable action")
                continue

            elif action["type"] == "set":
                setattr(target_class, action["function_name"], action["args"][0])
                logger.info("undo %s %s" % (action["function_name"], action["args"][0]))

            elif action["type"] == "schedule":
                # remove task manager
                er = EmailRule.objects.filter(id=action["args"][0])
                logger.debug(er)
                er.delete()

            elif action["type"] == "action":
                reverse_action = [("add_labels", "remove_labels"), ("mark_read", "mark_unread"), ("_move", "_move")]
                
                for r in reverse_action:
                    if action["function_name"] in r:
                        reverse_func = getattr(target_class, r[1]) if r[0] == action["function_name"] else getattr(target_class, r[0])
                        action["args"].reverse()
                        logger.info(action["args"])
                        reverse_func(*action["args"]) if action["args"] else reverse_func()

            elif action["type"] == "get":
                pass

        logschema.is_canceled = True
        logschema.save()

        res['status'] = True

    except IMAPClient.Error as e:
        logger.exception(e)
        res['code'] = e
    except MessageSchema.DoesNotExist:
        logger.exception("error here")
        res['code'] = "This message no longer exists in your inbox"
    except Exception as e:
        logger.exception(e)
        res['code'] = msg_code['UNKNOWN_ERROR']
    finally:
        imap.logout()

    logging.debug(res)
    return res

def handle_imap_idle(user, email, folder='INBOX'):
    return
    imap_account = ImapAccount.objects.get(email=email)

    watching_folder = FolderSchema.objects.get(imap_account=imap_account, name=folder)

    bc = ButtonChannel.objects.filter(watching_folder=watching_folder)
    if bc.exists() and timezone.now() - bc.latest('timestamp').timestamp < timezone.timedelta(seconds=3*60):    # there is something running so noop
        return

    while True:
		# <--- Start of IMAP server connection loop
		
		# Attempt connection to IMAP server
        button_logger.info('connecting to IMAP server - %s' % email)
        try:
            res = authenticate(imap_account)
            if not res['status']:
				return
				
            imap = res['imap']
            if "exchange" in imap_account.host or "csail" in imap_account.host:
			    imap.use_uid = False
        except Exception:
			# If connection attempt to IMAP server fails, retry
			etype, evalue = sys.exc_info()[:2]
			estr = traceback.format_exception_only(etype, evalue)
			logstr = 'failed to connect to IMAP server - '
			for each in estr:
				logstr += '{0}; '.format(each.strip('\n'))
			button_logger.error(logstr)
			sleep(10)
			continue
        button_logger.info('server connection established')

		# Select IMAP folder to monitor
        button_logger.info('selecting IMAP folder - {0}'.format(folder))
        try:
			result = imap.select_folder(folder)
			button_logger.info('folder selected')
        except Exception:
			# Halt script when folder selection fails
			etype, evalue = sys.exc_info()[:2]
			estr = traceback.format_exception_only(etype, evalue)
			logstr = 'failed to select IMAP folder - '
			for each in estr:
				logstr += '{0}; '.format(each.strip('\n'))
			button_logger.critical(logstr)
			break
		
		# latest_seen_UID = None
		# # Retrieve and process all unread messages. Should errors occur due
		# # to loss of connection, attempt restablishing connection 
		# try:
		# 	result = imap.search('UNSEEN')
		# 	latest_seen_UID = max(result)
		# except Exception:
		# 	continue
		# log.info('{0} unread messages seen - {1}'.format(
		# 	len(result), result
		# 	))
		
		# for each in result:
			# try:
			# 	# result = imap.fetch(each, ['RFC822'])
			# except Exception:
			# 	log.error('failed to fetch email - {0}'.format(each))
			# 	continue
			# mail = email.message_from_string(result[each]['RFC822'])
			# try:
			# 	# process_email(mail, download, log)
			# 	log.info('processing email {0} - {1}'.format(
			# 		each, mail['subject']
			# 		))
			# except Exception:
			# 	log.error('failed to process email {0}'.format(each))
			# 	raise
			# 	continue

        try: 		
			while True:
			    # <--- Start of mail monitoring loop

                # Create a new entry for watching this folder 
			    bc = ButtonChannel.objects.filter(watching_folder=watching_folder)
			    bc.delete()

			    bc_folder = ButtonChannel( watching_folder=watching_folder )
			    bc_folder.save()

			    # After all unread emails are cleared on initial login, start
			    # monitoring the folder for new email arrivals and process 
			    # accordingly. Use the IDLE check combined with occassional NOOP
			    # to refresh. Should errors occur in this loop (due to loss of
			    # connection), return control to IMAP server connection loop to
			    # attempt restablishing connection instead of halting script.
			    imap.idle()
			    result = imap.idle_check(3*60)  # timeout

			    # either mark as unread/read or new message
			    if result:
			        # EXISTS command mean: if the size of the mailbox changes (e.g., new messages)
			        button_logger.info(result)
			        imap.idle_done()
			        try:
			            uid = -1
			            if "exchange" in imap_account.host or "csail" in imap_account.host: # e.g., mit
			                flag = False
			                button_logger.info(result[0])
			                for r in result:
			                    if r[1] ==  "FETCH":
			                        flag = True
			                        result = [r[0]]

			                if not flag:
			                    continue
			            else: # e.g., gmail, gsuite
			                uid = result[0][2][1]
			                result = imap.search('UID %d' % uid)

			            button_logger.info(result)
			        except Exception as e:
			            # prevent reacting to msg move/remove 
			            button_logger.critical(e)
			            continue
                        
			        button_logger.info('{0} new unread messages - {1}'.format(
			            len(result),result
			            ))
			        for each in result:
			            _header_descriptor = 'BODY.PEEK[HEADER.FIELDS (SUBJECT)]'			            
			            # mail = email.message_from_string(
			            # 	fetch[each][_header_descriptor]
			            # 	)
			            try:
			                fetch = imap.fetch(each, [_header_descriptor, "UID"])

			                button_logger.info('processing email {0} - {1}'.format(
			                    each, fetch[each]
			                    ))
			                uid = -1
			                if "exchange" in imap_account.host or "csail" in imap_account.host:
			                    uid = fetch[each]["UID"]
			                else:
			                    uid = each
			                message = MessageSchema.objects.get(imap_account=imap_account, folder__name=folder, uid=uid)
			                button_logger.info(message.base_message.subject)
			                bc = ButtonChannel(message=message, imap_account=imap_account, code=ButtonChannel.OK)
			                bc.save()

			            except MessageSchema.DoesNotExist:
			                button_logger.error("Catch new messages but can't find the message %s " % fetch[each]) 
			                # TODO this creates a new instance of buttonchannel

			                bc = ButtonChannel(imap_account=imap_account, code=ButtonChannel.MSG_NOT_FOUND, log="Catch new messages but can't find the message %s " % fetch[each])
			                bc.save()
			            except Exception as e:
			                button_logger.error(str(e))
			                button_logger.error(
			                    'failed to process email {0}'.format(each))

			                bc = ButtonChannel(imap_account=imap_account, code=ButtonChannel.UNKNOWN, log=str(e))
			                bc.save()

			    else:   # After time-out && no operation 
			        imap.idle_done()
			        imap.noop()
			        button_logger.info('no new messages seen')      

			        return

			    # End of mail monitoring loop --->           
        except Exception as e:
		    button_logger.exception("Error while  %s" % str(e))
        finally:
		    # Remove the entry with this folder and terminate the request 
		    bc = ButtonChannel.objects.filter(watching_folder=watching_folder)
		    bc.delete()

		    imap.logout()

		    return

            
# def fetch_flag():
#     responses = conn.select_folder(self.name)
#     highest_mod_seq = responses.get(b'HIGHESTMODSEQ') if self.c.supports_condstore() else None
#     if b'NOMODSEQ' in responses:
#         highest_mod_seq = self.highest_mod_seq = None
#     if self.uid_validity is None or self.uid_validity != uid_validity:
#         self.clear_cache()
#         self.initial_s2c_sync(conn, uid_next)
#     else:
#         self.normal_s2c_sync(conn, uid_next, highest_mod_seq)