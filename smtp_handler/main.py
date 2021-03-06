import logging, time, base64, traceback, json, os
from salmon.routing import route, stateless
from salmon.mail import MailResponse
from config.settings import relay
from http_handler.settings import WEBSITE
from django.contrib.sites.models import Site
from http_handler.settings import PROTOCOL

from email.utils import *
from email import message_from_string, header, message
# from engine.main import *
from engine.s3_storage import upload_message
from utils import parseaddr, get_body
from django.db.utils import OperationalError
from datetime import datetime
import pytz
import django.db
from browser.imap import *
from browser.sandbox import interpret_bypass_queue
from imapclient import IMAPClient

from schema.youps import ImapAccount, MessageSchema, EmailRule, FolderSchema  # noqa: F401 ignore unused we use it for typing
from engine.models.mailbox import MailBox
from engine.models.message import Message
from engine.models.folder import Folder
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


logger = logging.getLogger("routing") # type: logging.Logger


@route("(address)@(host)", address=".+")
def START(message, address=None, host=None):

    logger.info("Email to mailbot@")

    arrived_message = message

    name, addr = parseaddr(arrived_message['from'].lower())
    site = Site.objects.get_current()
    auth_res = None
    # restart the db connection
    django.db.close_connection()
    
    try:
        addr = addr.strip()
        imapAccount = ImapAccount.objects.get(email=addr)

        er_to_execute = None
        ers = EmailRule.objects.filter(mode__imap_account=imapAccount, type='shortcut')
        for er in ers:
            if er.get_forward_addr().lower() == address.lower():
                er_to_execute = er
                break

        if not er_to_execute:
            body_part = []

            body = {}
            options = get_available_shortcut_link_text(imapAccount, site.domain) 
            body["text"] = "You email to %s@%s but this shortcut does not exist. \n\n %s \n\n Link to YouPS: %s://%s" % (address, host, options["text"], PROTOCOL, site.domain)
            body["html"] = "You email to %s@%s but this shortcut does not exist. <br><br> %s <br><br> Link to YouPS: <a href='%s://%s'>%s://%s</a>" % (address, host, options["html"], PROTOCOL, site.domain, PROTOCOL, site.domain)

            new_message = create_response(arrived_message, addr,arrived_message["message-id"], body, host)
            relay.deliver(new_message)
            return
            

        logging.debug("mailbot %s" % addr)
        auth_res = authenticate( imapAccount )
        if not auth_res['status']:
            raise ValueError('Something went wrong during authentication. Log in again at %s/editor' % host)
        imap = auth_res['imap']

        mailbox = MailBox(imapAccount, imap)

        # local shortcut
        if arrived_message["In-Reply-To"]:
            # Get the original message
            original_message_schema = MessageSchema.objects.filter(imap_account=imapAccount, base_message__message_id=arrived_message["In-Reply-To"])
            
            if original_message_schema.exists():
                original_message_schema = original_message_schema[0]

                imap.select_folder(original_message_schema.folder.name)           
                original_message = Message(original_message_schema, imap)
            else:
                # in case YouPS didn't register to DB yet, save the message to DB immediately 
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
                    raise ValueError("Email does not exist. The message is deleted or YouPS can't detect the message.")
                else: 
                    # Save this message immediately. so it can be ran when it is registered to the database  
                    try: 
                        logger.critical("%s %s" %(imapAccount.email, mail_found_at))
                        folder = mail_found_at

                        if original_message_id:
                            folder._save_new_messages(original_message_id[0], urgent=True)

                            original_message_schema = MessageSchema.objects.filter(imap_account=imapAccount, base_message__message_id=arrived_message["In-Reply-To"])
                            if not original_message_schema.exists():
                                raise
                            imap.select_folder(original_message_schema.folder.name)           
                            original_message = Message(original_message_schema, imap)

                    except FolderSchema.DoesNotExist, MessageSchema.DoesNotExist:
                        raise ValueError("Email does not exist. The message is deleted or YouPS can't detect the message.")

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
                
                res, body = run_shortcut(shortcuts, mailbox, original_message_schema, code_body)

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

                # new_message.set_payload(content.encode('utf-8')) 
                if "text" in body and "html" in body:
                    body["text"] = "Your command: %s%sResult: %s" % (code_body, "\n\n", body["text"])
                    body["html"] = "Your command: %s%sResult: %s" % (code_body, "<br><br>", body["html"])
                else: 
                    body["text"] = "Your command:%s%sResult:%s" % (code_body, "\n\n", body["text"])

                new_message = create_response(arrived_message, addr, original_message_schema.message_id, body, host)

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
                except Exception:
                    logger.critical("error adding logs")

                imap.append(original_message_schema.folder.name, str(new_message))
                # instead of sending email, just replace the forwarded email to arrive on the inbox quietly
        
        

        # global shortcut
        else:
            logger.info("global shortcut")

            # get any message
            original_message_schema = MessageSchema.objects.filter(imap_account=imapAccount).last()
            res, body = run_shortcut([er_to_execute], mailbox, original_message_schema, "")

            # parseaddr(arrived_message['subject'])
        
            logger.info(res)
            logger.info(body)

            new_message = create_response(arrived_message, addr,arrived_message["message-id"], body, host)
            relay.deliver(new_message)

    except ImapAccount.DoesNotExist:
        body_part = []
        body = {}
        body["text"] = 'Your email %s is not registered or stopped due to an error. Write down your own email rule at %s://%s' % (addr, PROTOCOL, site.domain)
        body["html"] = 'Your email %s is not registered or stopped due to an error. Write down your own email rule at <a href="%s://%s">%s://%s</a>' % (addr, PROTOCOL, site.domain, PROTOCOL, site.domain)
        
        mail = create_response(arrived_message, addr, arrived_message["message-id"], body, host)
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

def create_response(arrived_message, to, in_reply_to=None, body={"text":"", "body":""}, host="youps.csail.mit.edu"):
    new_message = MIMEMultipart('alternative')
    new_message["Subject"] = "Re: " + arrived_message["subject"]
    new_message["From"] = WEBSITE+"@" + host
    new_message["In-Reply-To"] = in_reply_to if in_reply_to else arrived_message["message-id"]
    new_message["To"] = to

    part1 = MIMEText(body["text"].encode('utf-8'), 'plain')
    part2 = MIMEText(body["html"].encode('utf-8'), 'html')

    new_message.attach(part1)
    new_message.attach(part2)

    return new_message

def get_available_shortcut_link_text(imapAccount, domain_name):
    shortcuts = EmailRule.objects.filter(mode__imap_account=imapAccount, type='shortcut')

    if not shortcuts.exists():
        return {"text": "You don't have any shortcut available.", "html": "You don't have any shortcut available."}
        
    body = {"text": "Your shortcut list\n\n", "html": "Your shortcut list<br><br>"}

    for shortcut in shortcuts:
        shortcut_addr = "%s@%s" % (shortcut.get_forward_addr(), domain_name)
     
        body["text"] += "* %s: %s\n" % (shortcut.name, shortcut_addr)
        body["html"] += "* %s: <a href='mailto:%s?subject=YouPS shortcut&body=contact address: <HERE>'>%s</a><br>" % (shortcut.name, shortcut_addr, shortcut_addr)


    return body


def run_shortcut(shortcuts, mailbox, original_message_schema, code_body):
    body = {"text": "", "html": ""}
    res = None
    for shortcut in shortcuts:
        extra_info={"msg-id": original_message_schema.id, "code": shortcut.code, "shortcut": code_body}

        res = interpret_bypass_queue(mailbox, extra_info={"msg-id": original_message_schema.id, "code": shortcut.code, "shortcut": code_body})
        logger.debug(res)

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

    return res, body

@route("(address)@(host)", address="help", host=".+")
def help(message, address=None, host=None):
    logger.info("Email to mailbot@%s" % HOST)

    try: 
        name, addr = parseaddr(message['from'].lower())
        imapAccount = ImapAccount.objects.get(email=addr)

        to_addr = message['From']
        from_addr = address + '@' + HOST
        subject = "YouPS Help"
        body = "Welcome to YouPS."

        ers = EmailRule.objects.filter(mode__imap_account=imapAccount, type='shortcut')
        if ers.exists():
            body += " Please find below a general help on managing your email shortcut.\n\n"
            for er in ers:
                body += "%s: <a href='mailto:%s'>%s</a>" % (er.name, er.get_forward_addr() +  "@" + host, er.get_forward_addr() +  "@" + host)
        else:
            body += "\nThere is no shortcut defined at the moment. Create your shortcut here: <a href='%s://%s'>%s://%s</a>" % (PROTOCOL, site.domain, PROTOCOL, site.domain)
    
        mail = MailResponse(From = from_addr, To = to_addr, Subject = subject, Body = body)
        relay.deliver(mail)
    except ImapAccount.DoesNotExist:
        subject = "YouPS registeration required"
        error_msg = 'Your email %s is not registered. Create your account here: %s://%s' % (addr, PROTOCOL, site.domain)
        mail = MailResponse(From = WEBSITE+"@" + host, To = addr, Subject = subject, Body = error_msg)
        relay.deliver(mail)
    except Exception as e:
        logger.exception(str(e))
    


@route("(address)@(host)", address=".+", host=".+")
def send_account_info(message, address=None, host=None):

    subj_string = message['Subject'].encode('utf-8').lower()
    activation_str = ("account activation on %s" % WEBSITE).lower()
    reset_str = ("password reset on %s" % WEBSITE).lower()

    logging.debug(message['Subject'])
    logging.debug(message['To'])
    logging.debug(message['From'])
    email_message = message_from_string(str(message))
    msg_text = get_body(email_message)
    logging.info(msg_text)

    if message['From'].encode('utf-8') == NO_REPLY and (activation_str in subj_string or reset_str in subj_string):
        
        email_message = email.message_from_string(str(message))
        msg_text = get_body(email_message)
        mail = MailResponse(From = NO_REPLY, To = message['To'], Subject = message['Subject'], Body = msg_text['plain'])
        relay.deliver(mail)