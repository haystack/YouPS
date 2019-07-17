import sys
import base64
import logging
import random
import string
import traceback
import datetime

from Crypto.Cipher import AES
from imapclient import IMAPClient

from django.utils import timezone
from browser.imap import GoogleOauth2, authenticate
from engine.models.mailbox import MailBox
from browser.sandbox import interpret_bypass_queue 
from engine.constants import msg_code
from http_handler.settings import IMAP_SECRET
from schema.youps import (FolderSchema, ImapAccount, MailbotMode, MessageSchema, EmailRule, EmailRule_Args, ButtonChannel)
from engine.models.message import Message  # noqa: F401 ignore unused we use it for typing

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

    return res

def apply_button_rule(user, email, er_id, msg_schema_id, kargs):
	res = {'status' : False}
	
	try:
		logger.info("here")
		imapAccount = ImapAccount.objects.get(email=email)
		auth_res = authenticate( imapAccount )
		if not auth_res['status']:
		    raise ValueError('Something went wrong during authentication. Refresh and try again!')

		imap = auth_res['imap']  # noqa: F841 ignore unused

        #  read from DB and convert to the type accordingly 
		for key, value in kargs.iteritems():
		    er_arg = EmailRule_Args.objects.get(rule__mode__imap_account=imapAccount, name=key)
		    if er_arg.type == "datetime":
		        kargs[key] = datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M')

		mailbox = MailBox(imapAccount, imap, is_simulate=False)
		er = EmailRule.objects.get(id=er_id)
		res = interpret_bypass_queue(mailbox, extra_info={"msg-id": msg_schema_id, "code": er.code, "shortcut": kargs, "rule_name": er.name})
		
		res['status'] = True
	
	except ImapAccount.DoesNotExist:
	    res['code'] = "Error during deleting the mode. Please refresh the page."
	except MailbotMode.DoesNotExist:
	    res['code'] = "Error during deleting the mode. Please refresh the page."
	except Exception as e:
	    logger.exception(e)
	    res['code'] = msg_code['UNKNOWN_ERROR']
	return res
    
def create_mailbot_mode(user, email, push=True):
	res = {'status' : False}
	
	try:
	    imapAccount = ImapAccount.objects.get(email=email)
	    mm = MailbotMode(imap_account=imapAccount)
	    mm.save()
	
	    res["mode-id"] = mm.id
	    res['status'] = True
	
	except ImapAccount.DoesNotExist:
	    res['code'] = "Error during deleting the mode. Please refresh the page."
	except MailbotMode.DoesNotExist:
	    res['code'] = "Error during deleting the mode. Please refresh the page."
	except Exception, e:
	    logger.exception(res)
	    res['code'] = msg_code['UNKNOWN_ERROR']
	return res

def delete_mailbot_mode(user, email, mode_id, push=True):
    res = {'status' : False}
    
    try:
        imapAccount = ImapAccount.objects.get(email=email)
        mm = MailbotMode.objects.get(id=mode_id, imap_account=imapAccount)
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
        logger.exception(res)
        res['code'] = msg_code['UNKNOWN_ERROR']
    
    return res


def fetch_watch_message(user, email, folder_name):
    res = {'status' : False}

    try:
        imapAccount = ImapAccount.objects.get(email=email)
        bc = ButtonChannel.objects.filter(message__imap_account=imapAccount).filter(message__folder__name=folder_name).latest('timestamp')
        res['folder'] = bc.message.folder.name
        res['uid'] = bc.message.id 

        message = Message(bc.message, imap_client="")   # since we are only extracting metadata, no need to use imap_client
        res['message'] = message._get_meta_data_friendly() 
        res['sender'] = message._get_from_friendly()
        res['watch_status'] = ButtonChannel.objects.filter(watching_folder__imap_account=imapAccount).filter(watching_folder__name=folder_name).exists()

        res['status'] = True

    except ImapAccount.DoesNotExist:
        res['code'] = "Error during authentication. Please refresh"
    except ButtonChannel.DoesNotExist:
        res['uid'] = 0
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
        er = EmailRule.objects.filter(id=rule_id, mode__imap_account=imap_account)

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
        # uid = fetch_latest_email_id(imapAccount, imap)'
        # imapAccount.newest_msg_id = uid

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
                mailbotMode.name = mode_name
                mailbotMode.save()
            else:
                mailbotMode = MailbotMode(name=mode_name, imap_account=imapAccount)
                mailbotMode.save()

            # Remove old editors to re-save it
            # TODO  dont remove it
            er = EmailRule.objects.filter(mode=mailbotMode)
            logger.debug("deleting er editor run request")
            args = EmailRule_Args.objects.filter(rule=er)
            args.delete()
            er.delete()

            for value in mode['editors']:
                name = value['name'].encode('utf-8')
                code = value['code'].encode('utf-8')
                folders = value['folders']
                logger.info(value)
                
                er = EmailRule(name=name, mode=mailbotMode, type=value['type'], code=code)
                er.save()

                # Save selected folder for the mode
                for f in folders:
                    folder = FolderSchema.objects.get(imap_account=imapAccount, name=f)
                    logger.info("saving folder to the editor %s run request" % folder.name)
                    er.folders.add(folder)

                er.save()

                # Save shortcut email args
                if value['type'] == "shortcut":
                    for arg in value['args']:
                        logger.info(arg)
                        
                        new_arg = EmailRule_Args(type=arg['type'], rule=er)
                        if arg['name']:
                            new_arg.name = arg['name']
                        new_arg.save()
                

            logger.info(EmailRule.objects.filter(mode=mailbotMode).values('name', 'id'))
        

        if run_request:
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

    except IMAPClient.Error, e:
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

def handle_imap_idle(user, email, folder='INBOX'):
    imap_account = ImapAccount.objects.get(email=email)

    watching_folder = FolderSchema.objects.get(imap_account=imap_account, name=folder)

    bc = ButtonChannel.objects.filter(watching_folder=watching_folder)
    if bc.exists() and timezone.now() - bc.latest('timestamp').timestamp < timezone.timedelta(seconds=3*60):    # there is something running so noop
        return

    while True:
		# <--- Start of IMAP server connection loop
		
		# Attempt connection to IMAP server
		logger.info('connecting to IMAP server - %s' % email)
		try:
			res = authenticate(imap_account)
			if not res['status']:
				return
				
			imap = res['imap']
		except Exception:
			# If connection attempt to IMAP server fails, retry
			etype, evalue = sys.exc_info()[:2]
			estr = traceback.format_exception_only(etype, evalue)
			logstr = 'failed to connect to IMAP server - '
			for each in estr:
				logstr += '{0}; '.format(each.strip('\n'))
			logger.error(logstr)
			sleep(10)
			continue
		logger.info('server connection established')

		# Select IMAP folder to monitor
		logger.info('selecting IMAP folder - {0}'.format(folder))
		try:
			result = imap.select_folder(folder)
			logger.info('folder selected')
		except Exception:
			# Halt script when folder selection fails
			etype, evalue = sys.exc_info()[:2]
			estr = traceback.format_exception_only(etype, evalue)
			logstr = 'failed to select IMAP folder - '
			for each in estr:
				logstr += '{0}; '.format(each.strip('\n'))
			logger.critical(logstr)
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

			    bc = ButtonChannel( watching_folder=watching_folder )
			    bc.save()
			    
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
			        logger.info(result)
			        imap.idle_done()
			        result = imap.search('UID %d' % result[0][2][1])
			        logger.info('{0} new unread messages - {1}'.format(
			            len(result),result
			            ))
			        for each in result:
			            _header_descriptor = 'BODY.PEEK[HEADER.FIELDS (SUBJECT)]'
			            fetch = imap.fetch(each, [_header_descriptor])
			            # mail = email.message_from_string(
			            # 	fetch[each][_header_descriptor]
			            # 	)
			            try:
			                # process_email(mail, download, log)
			                logger.info('processing email {0} - {1}'.format(
			                    each, fetch[each]
			                    ))
			                message = MessageSchema.objects.get(imap_account=imap_account, folder__name=folder, uid=each)
			                bc = ButtonChannel(message=message)
			                logger.exception(message.base_message.subject)
			                bc.save()

			            except MessageSchema.DoesNotExist:
			                logger.error("Catch new messages but can't find the message %s " % fetch[each])
			            except Exception:
			                logger.error(
			                    'failed to process email {0}'.format(each))
			                raise
			                continue
			    else:   # After time-out && no operation 
			        imap.idle_done()
			        imap.noop()
			        logger.info('no new messages seen')      

			        return

			    # End of mail monitoring loop --->           
		except Exception as e:
		    logger.exception("Error while  %s" % str(e))
		finally:
		    # Remove the entry with this folder and terminate the request 
		    bc = ButtonChannel.objects.filter(watching_folder=watching_folder)
		    bc.delete()

		    imap.logout()

		    return

            
