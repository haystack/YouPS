import logging, time, base64, traceback, json
from lamson.routing import route, stateless
from config.settings import relay
from http_handler.settings import WEBSITE
from django.contrib.sites.models import Site
from http_handler.settings import PROTOCOL
from schema.models import *
from schema.models import ImapAccount
from lamson.mail import MailResponse
from email.utils import *
from email import message_from_string, header, message
from engine.main import *
from engine.s3_storage import upload_message
from utils import *
from django.db.utils import OperationalError
from datetime import datetime
import pytz
import django.db
from browser.imap import *
from browser.sandbox import interpret_bypass_queue
from imapclient import IMAPClient
from schema.youps import MessageSchema, EmailRule, FolderSchema  # noqa: F401 ignore unused we use it for typing
from engine.models.mailbox import MailBox
from engine.models.message import Message
from engine.models.folder import Folder
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


'''
Murmur Mail Interface Handler

@author: Anant Bhardwaj
@date: Oct 20, 2012
'''

logger = logging.getLogger('youps')  # type: logging.Logger

@route("(address)@(host)", address=".+", host=".+")
@stateless
def mailbot(arrived_message, address=None, host=None):
    # no public groups to list on squadbox. 
    if WEBSITE == 'squadbox' or WEBSITE == 'murmur':
        logging.debug("Ignored message to all@%s, no public groups to list" % HOST)
        return

    else:
        logger.info("Email to mailbot@%s" % HOST)

        name, addr = parseaddr(arrived_message['from'].lower())
        site = None
        # restart the db connection
        django.db.close_connection()
        
        try:
            site = Site.objects.get_current()
            addr = addr.strip()
            imapAccount = ImapAccount.objects.get(email=addr)
            logging.debug("mailbot %s" % addr)
            auth_res = authenticate( imapAccount )
            if not auth_res['status']:
                raise ValueError('Something went wrong during authentication. Log in again at %s/editor' % host)

            imap = auth_res['imap']

            mailbox = MailBox(imapAccount, imap)

            # Get the original message
            original_message_schema = MessageSchema.objects.filter(imap_account=imapAccount, message_id=arrived_message["In-Reply-To"])
            if original_message_schema.exists():
                original_message_schema = original_message_schema[0]

                imap.select_folder(original_message_schema.folder.name)           
                original_message = Message(original_message_schema, imap)
            else:
                # in case YoUPS didn't register to DB yet, save the message to DB immediately 
                mail_found_at = ""
                original_message_id = -1
                for folder in mailbox._list_selectable_folders():
                    imap.select_folder(folder.name)
                    original_message_id = imap.search(["HEADER", "Message-ID", arrived_message["In-Reply-To"]])

                    # original_message

                    if original_message_id:
                        mail_found_at = folder
                        break
                
                if not mail_found_at:
                    raise ValueError("Email does not exist. The message is deleted or YoUPS can't detect the message.")
                else: 
                    # Save this message immediately. so it can be ran when it is registered to the database  
                    try: 
                        logger.critical("%s %s" %(imapAccount.email, mail_found_at))
                        folder = mail_found_at

                        if original_message_id:
                            folder._save_new_messages(original_message_id[0], urgent=True)

                            original_message_schema = MessageSchema.objects.filter(imap_account=imapAccount, message_id=arrived_message["In-Reply-To"])
                            if not original_message_schema.exists():
                                raise
                            imap.select_folder(original_message_schema.folder.name)           
                            original_message = Message(original_message_schema, imap)

                    except FolderSchema.DoesNotExist, MessageSchema.DoesNotExist:
                        raise ValueError("Email does not exist. The message is deleted or YoUPS can't detect the message.")


            entire_message = message_from_string(str(arrived_message))
            entire_body = get_body(entire_message)

            code_body = entire_body['plain'][:(-1)*len(original_message.content['text'])]
            gmail_header = "---------- Forwarded message ---------"
            if gmail_header in code_body:
                code_body = code_body.split(gmail_header)[0].strip()
            logging.debug(code_body)

            shortcuts = EmailRule.objects.filter(mode=imapAccount.current_mode, type="shortcut")
            if not imapAccount.current_mode or not shortcuts.exists():
                body = "Your YouPS hasn't turned on or don't have email shortcuts yet! Define your shortcuts here %s://%s" % (PROTOCOL, site.domain)

                mail = MailResponse(From = WEBSITE+"@" + host, To = imapAccount.email, Subject = "Re: " + original_message.subject, Body = body)
                relay.deliver(mail)

            else:
                
                body = {"text": "", "html": ""}
                for shortcut in shortcuts:
                    res = interpret_bypass_queue(mailbox, None, extra_info={"msg-id": original_message_schema.id, "code": shortcut.code, "shortcut": code_body})
                    logging.debug(res)

                    for key, value in res['appended_log'].iteritems():
                        if not value['error']:
                            body["text"] = 'Your mail shortcut is successfully applied! \n'
                            body["html"] = 'Your mail shortcut is successfully applied! <br>'
                        else:
                            body["text"] = 'Something went wrong! \n'
                            body["html"] = 'Something went wrong! <br>'
                        
                        body["text"] = body["text"] + value['log']
                        body["html"] = body["html"] + value['log']
                
                    logger.debug(body)

                # Go to sent folder and delete the sent function from user  
                if imapAccount.is_gmail:
                    imap.select_folder('[Gmail]/Sent Mail')
                else:
                    import imapclient
                    sent = imap.find_special_folder(imapclient.SENT)
                    if sent is not None:
                        imap.select_folder(sent)
                this_message = imap.search(["HEADER", "In-Reply-To", original_message_schema.message_id])
                imap.delete_messages(this_message)

                new_message = MIMEMultipart('alternative')
                new_message["Subject"] = "Re: " + arrived_message["subject"]
                new_message["From"] = WEBSITE+"@" + host
                new_message["In-Reply-To"] = original_message_schema.message_id

        
                try:
                    new_msg = {}
                    from_field = original_message._get_from_friendly()

                    to_field = original_message._get_to_friendly()

                    cc_field = original_message._get_cc_friendly()

                    new_msg["timestamp"] = str(datetime.now().strftime("%m/%d %H:%M:%S,%f"))
                    new_msg["type"] = "new_message"
                    new_msg["from_"] = from_field
                    new_msg["to"] = to_field
                    new_msg["cc"] = cc_field
                    new_msg["trigger"] = "shortcut"
                    new_msg["log"] = body["text"]
                    new_msg.update(original_message._get_meta_data_friendly())
                    log_decoded = json.loads(imapAccount.execution_log) if len(imapAccount.execution_log) else {}
                    log_decoded[new_msg["timestamp"]] = new_msg

                    imapAccount.execution_log = json.dumps(log_decoded)
                    imapAccount.save()
                except Exception:
                    logger.critical("error adding logs")

                # new_message.set_payload(content.encode('utf-8')) 
                if "text" in body and "html" in body:
                    body["text"] = "Your command: %s%sResult: %s" % (code_body, "\n\n", body["text"])
                    body["html"] = "Your command: %s%sResult: %s" % (code_body, "<br><br>", body["html"])
                    part1 = MIMEText(body["text"].encode('utf-8'), 'plain')
                    part2 = MIMEText(body["html"].encode('utf-8'), 'html')
                    new_message.attach(part1)
                    new_message.attach(part2)
                else: 
                    body["text"] = "Your command:%s%sResult:%s" % (code_body, "\n\n", body["text"])
                    part1 = MIMEText(body["text"].encode('utf-8'), 'plain')
                    new_message.attach(part1)

                imap.append(original_message_schema.folder.name, str(new_message))
                # instead of sending email, just replace the forwarded email to arrive on the inbox quietly

        except ImapAccount.DoesNotExist:
            subject = "YoUPS shortcuts Error"
            error_msg = 'Your email %s is not registered or stopped due to an error. Write down your own email rule at %s://%s' % (addr, PROTOCOL, site.domain)
            mail = MailResponse(From = WEBSITE+"@" + host, To = arrived_message['From'], Subject = subject, Body = error_msg)
            relay.deliver(mail)
        except Exception, e:
            logger.exception("Error while executing %s %s " % (e, traceback.format_exc()))
            subject = "[YoUPS] shortcuts Errors"
            mail = MailResponse(From = WEBSITE+"@" + host, To = arrived_message['From'], Subject = subject, Body = str(e))
            relay.deliver(mail)
        finally:
            if auth_res and auth_res['status']:
                # Log out after after conduct required action
                imap.logout()
        

@route("(group_name)\\+info@(host)", group_name=".+", host=HOST)
@stateless
def info(message, group_name=None, host=None):

    # for now I'm not sure what we would have here, 
    # but we can change this later on.
    if WEBSITE == 'squadbox':
        logging.debug("No group info sent via email in Squadbox")
        return

    elif WEBSITE == 'murmur':
        group_name = group_name.lower()
        res = group_info(group_name)
        subject = "Group Info -- Success"
        body = "Group info for %s:\n" %(group_name)
        if(res['status']):
            body = "Group Name: %s@%s, Active: %s\n\n" %(res['group_name'], host, res['active'])
            for member in res['members']:           
                body += "%s : %s\n" %('Email: ', member['email'])
                body += "%s : %s\n" %('Active: ', member['active'])
                body += "%s : %s\n" %('Member: ', member['member'])
                body += "%s : %s\n" %('Guest: ', member['guest'])
                body += "%s : %s\n" %('Moderator: ', member['moderator'])
                body += "%s : %s\n" %('Admin: ', member['admin'])
            body += "\n..........................\n"       
        else:
            subject = "Group Info -- Error"
            body = "Error Message: %s" %(res['code'])
            
        mail = MailResponse(From = NO_REPLY, To = message['From'], Subject = subject, Body = body)
        relay.deliver(mail)

@route("(address)@(host)", address="help", host=HOST)
@stateless
def help(message, address=None, host=None):

    if WEBSITE == 'squadbox':
        # we should change this to actually send a useful help email
        # with the possible via-email commands in squadbox
        return

    elif WEBSITE == 'murmur':
        to_addr = message['From']
        from_addr = address + '@' + HOST
        subject = "Help"
        body = "Welcome to %s. Please find below a general help on managing a group mailing list.\n\n" %(host)
        body += "To create a new group: <name>+create@%s\n" %(host)
        body += "To activate/re-activate your group: <name>+activate@%s\n" %(host)
        body += "To de-activate your group: <name>+deactivate@%s\n" %(host)
        body += "To subscribe to a group: <name>+subscribe@%s\n" %(host)
        body += "To unsubscribe from a group: <name>+unsubscribe@%s\n" %(host)
        body += "To see details of a group: <name>+info@%s\n" %(host)
        body += "To see a listing of all the groups: all@%s\n" %(host)
        body += "To get help: help@%s\n" %(host)
        body += "To post message to a group: <name>@%s\n\n" %(host)
        body += "Please substitute '<name>' with your group name."  
        mail = MailResponse(From = from_addr, To = to_addr, Subject = subject, Body = body)
        relay.deliver(mail)
        return


@route("(address)@(host)", address=".+", host=".+")
@stateless
def send_account_info(message, address=None, host=None):

    subj_string = message['Subject'].encode('utf-8').lower()
    activation_str = ("account activation on %s" % WEBSITE).lower()
    reset_str = ("password reset on %s" % WEBSITE).lower()

    logging.debug(message['Subject'])
    logging.debug(message['To'])
    logging.debug(message['From'])

    if message['From'].encode('utf-8') == NO_REPLY and (activation_str in subj_string or reset_str in subj_string):
        
        email_message = email.message_from_string(str(message))
        msg_text = get_body(email_message)
        mail = MailResponse(From = NO_REPLY, To = message['To'], Subject = message['Subject'], Body = msg_text['plain'])
        relay.deliver(mail)
