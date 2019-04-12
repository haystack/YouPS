from __future__ import unicode_literals, division

import logging
import sys, traceback
import datetime
import copy
import typing as t  # noqa: F401 ignore unused we use it for typing
from StringIO import StringIO
from email import message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing
from schema.youps import MessageSchema  # noqa: F401 ignore unused we use it for typing

from engine.models.event_data import NewMessageData, NewMessageDataScheduled
from engine.models.mailbox import MailBox  # noqa: F401 ignore unused we use it for typing
from engine.models.message import Message
from engine.models.contact import Contact
from smtp_handler.utils import send_email

logger = logging.getLogger('youps')  # type: logging.Logger


def interpret(mailbox, mode, is_simulate=False, simulate_info={}):
    """This function executes users' code.  

        Args:
            mailbox (Mailbox): user's mailbox
            mode (MailbotMode or None): if mode is null, it will bypass executing user's code and just print logs
            is_simulate (boolean): if True, it looks into simulate_info to test run user's code
            simulate_info (dict): it includes code, which is to be test ran, and msg-id, which is a id field of MessageSchema 
    """
    # type: (MailBox, MailbotMode, bool) -> t.Dict[t.AnyStr, t.Any]

    from schema.youps import EmailRule, MailbotMode
    from smtp_handler.utils import is_gmail

    # set up the default result
    res = {'status': True, 'imap_error': False, 'imap_log': ""}

    # if mode is None:
    #     logger.warn("No mode set for interpret")
    #     res['status'] = False
    #     return res

    # assert we actually got a mailbox
    assert isinstance(mailbox, MailBox)
    # assert the mode is the mailboat mode
    # assert isinstance(mode, MailbotMode)
    assert mailbox.new_message_handler is not None

    # define user methods
    def create_draft(subject="", to="", cc="", bcc="", content="", draft_folder="Drafts"):
        """Create a draft message and save it to user's draft folder

            Args:
                subject (string): the subject line of the draft message
                to (a single instance|list of string|Contact): addresses that go in to field
                cc (a single instance|list of string|Contact): addresses that go in cc field
                bcc (a single instance|list of string|Contact): addresses that go in bcc field
                content (string): content of the draft message 
                draft_folder (string): a name of draft folder 
        """
        
        new_message = MIMEMultipart('alternative')
        new_message["Subject"] = subject

        if isinstance(to, list):
            to_string = []
            for t in to:
                logger.info(isinstance(t, Contact))
                if isinstance(t, Contact):
                    to_string.append(t.email)
                else:
                    to_string.append(t)

            to = ",".join(to_string)
        else:
            if isinstance(to, Contact):
                to = to.email 

        if type(cc) == 'list':
            cc_string = []
            for t in cc:
                if isinstance(t, Contact):
                    cc_string.append(t.email)
                else:
                    cc_string.append(t)

            cc = ",".join(cc_string)
        else:
            if isinstance(cc, Contact):
                cc = cc.email 

        if type(bcc) == 'list':
            bcc_string = []
            for t in bcc:
                if isinstance(t, Contact):
                    bcc_string.append(t.email)
                else:
                    bcc_string.append(t)

            bcc = ",".join(bcc_string)
        else:
            if isinstance(bcc, Contact):
                bcc = bcc.email
         
        new_message["To"] = to
        new_message["Cc"] = cc
        new_message["Bcc"] = bcc
        logger.info(to)
        logger.info(cc)
        logger.info(bcc)
        # new_message.set_payload(content.encode('utf-8')) 
        if "text" in content and "html" in content:
            part1 = MIMEText(content["text"].encode('utf-8'), 'plain')
            part2 = MIMEText(content["html"].encode('utf-8'), 'html')
            new_message.attach(part1)
            new_message.attach(part2)
        else: 
            part1 = MIMEText(content, 'plain')
            new_message.attach(part1)

        if not is_simulate:
            if mailbox._imap_account.is_gmail:
                mailbox._imap_client.append('[Gmail]/Drafts', str(new_message))
                
            else:
                try:
                    # if this imap service provides list capability takes advantage of it
                    if [l[0][0] for l in mailbox._imap_client.list_folders()].index('\\Drafts'):
                        mailbox._imap_client.append(mailbox._imap_client.list_folders()[2][2], str(new_message))
                except Exception as e:
                    # otherwise try to guess a name of draft folder
                    try:
                        mailbox._imap_client.append('Drafts', str(new_message))
                    except IMAPClient.Error, e:
                        try:
                            mailbox._imap_client.append('Draft', str(new_message))
                        except IMAPClient.Error, e:
                            if "append failed" in e:
                                mailbox._imap_client.append(draft_folder, str(new_message))
        
        logger.debug("create_draft(): Your draft %s has been created" % subject)

    def create_folder(folder_name):
        if not is_simulate: 
            mailbox._imap_client.create_folder( folder_name )

        logger.debug("create_folder(): A new folder %s has been created" % folder_name)

    def rename_folder(old_name, new_name):
        if not is_simulate: 
            mailbox._imap_client.rename_folder( old_name, new_name )

        logger.debug("rename_folder(): Rename a folder %s to %s" % (old_name, new_name))

    def on_message_arrival(func):
        mailbox.new_message_handler += func

    def set_interval(interval=None, func=None):
        pass

    def send(subject="", to="", body="", smtp=""):  # TODO add "cc", "bcc"
        if len(to) == 0:
            raise Exception('send(): recipient email address is not provided')

        if not is_simulate:
            send_email(subject, mailbox._imap_account.email, to, body)
        logger.debug("send(): sent a message to  %s" % str(to))

    # get the logger for user output
    userLogger = logging.getLogger('youps.user')  # type: logging.Logger
    # get the stream handler associated with the user output
    userLoggerStreamHandlers = filter(lambda h: isinstance(h, logging.StreamHandler), userLogger.handlers)
    userLoggerStream = userLoggerStreamHandlers[0].stream if userLoggerStreamHandlers else None
    assert userLoggerStream is not None

    # create a string buffer to store stdout
    user_std_out = StringIO()

    # execute user code
    try:
        # set the stdout to a string
        sys.stdout = user_std_out

        # set the user logger to
        userLoggerStream = user_std_out

        from schema.youps import FolderSchema
        
        # define the variables accessible to the user
        user_environ = {
            'create_draft': create_draft,
            'create_folder': create_folder,
            'on_message_arrival': on_message_arrival
            # 'set_interval': set_interval
        }
        new_log = {}

        # simulate request. normally from UI
        if is_simulate:
            code = simulate_info['code']
            message_schema = MessageSchema.objects.filter(id=simulate_info['msg-id'])
            # temp get random message
            res['appended_log'] = {}

            for m_schema in message_schema:
                msg_log = {"log": ""}

                # create a read-only message object to prevent changing the message
                new_message = Message(m_schema, mailbox._imap_client, is_simulate=True)
                            
                user_environ['new_message'] = new_message
                try:
                    mailbox._imap_client.select_folder(m_schema.folder_schema.name)

                    # execute the user's code
                    if "on_message" in code:
                        exec(code + "\non_message(new_message)", user_environ)    

                    elif "on_flag_change" in code:
                        user_environ['new_flag'] = 'test-flag'
                        exec(code + "\non_flag_change(new_message, new_flag)", user_environ)    
                except Exception as e:
                    # Get error message for users if occurs
                    # print out error messages for user 
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    logger.info(e)
                    logger.info(exc_obj)
                    # logger.info(traceback.print_exception())

                    # TODO find keyword 'in on_message' or on_flag_change
                    # logger.info(traceback.format_tb(exc_tb))
                    # logger.info(sys.exc_info())
                        
                    msg_log["log"] = str(e)
                    msg_log["error"] = True 
                finally:         
                    # copy_msg["trigger"] = rule.name
                            
                    msg_log["log"] = "%s\n%s" % (user_std_out.getvalue(), msg_log["log"])
                    res['appended_log'][m_schema.id] = msg_log

                    # flush buffer
                    user_std_out = StringIO()

                    # set the stdout to a string
                    sys.stdout = user_std_out

                    # set the user logger to
                    userLoggerStream = user_std_out

        # regular loading from event queue
        else:
            # iterate through event queue
            for event_data in mailbox.event_data_list:
                new_msg = {}

                # event for new message arrival
                # TODO maybe caputre this info after execute log?
                if isinstance(event_data, NewMessageData) or isinstance(event_data, NewMessageDataScheduled):
                    from_field = {}
                    if event_data.message.from_._schema:
                        from_field = {
                            "name": event_data.message.from_.name,
                            "email": event_data.message.from_.email,
                            "organization": event_data.message.from_.organization,
                            "geolocation": event_data.message.from_.geolocation
                        }

                    to_field = [{
                        "name": t.name,
                        "email": t.email,
                        "organization": t.organization,
                        "geolocation": t.geolocation
                    } for t in event_data.message.to]

                    cc_field = [{
                        "name": t.name,
                        "email": t.email,
                        "organization": t.organization,
                        "geolocation": t.geolocation
                    } for t in event_data.message.cc]

                    # This is to log for users
                    new_msg = {
                        "timestamp": str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f")),
                        "type": "new_message", 
                        "folder": event_data.message.folder.name, 
                        "from_": from_field, 
                        "subject": event_data.message.subject, 
                        "to": to_field,
                        "cc": cc_field,
                        "flags": [f.encode('utf8', 'replace') for f in event_data.message.flags],
                        "date": str(event_data.message.date),
                        "deadline": event_data.message.deadline, 
                        "is_read": event_data.message.is_read, 
                        "is_deleted": event_data.message.is_deleted, 
                        "is_recent": event_data.message.is_recent,
                        "log": ""
                    }

                # if tho the engine is not turned on yet, still leave the log of message arrival 
                # TODO fix this. should be still able to show incoming message when there is mode exists and no rule triggers it 
                if mode is None:
                    new_log[new_msg["timestamp"]] = new_msg
                    continue

                # TODO maybe use this instead of mode.rules
                for rule in EmailRule.objects.filter(mode=mode):
                    is_fired = False 
                    copy_msg = copy.deepcopy(new_msg)
                    copy_msg["timestamp"] = str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f"))

                    assert isinstance(rule, EmailRule)

                    valid_folders = rule.folders.all()
                    valid_folders = FolderSchema.objects.filter(imap_account=mailbox._imap_account, rules=rule)
                    code = rule.code
                    
                    logger.debug(code)

                    # add the user's functions to the event handlers
                    if rule.type.startswith("new-message"):
                        code = code + "\non_message_arrival(on_message)"
                    # else:
                    #     continue
                    #     # some_handler or something += repeat_every

                    
                    try:
                        # execute the user's code
                        # exec cant register new function (e.g., on_message_arrival) when there is a user_env
                        exec(code, user_environ)

                        # Check if the type of rule and event_data match
                        if (type(event_data).__name__ == "NewMessageData" and rule.type =="new-message") or \
                                (type(event_data).__name__ == "NewMessageDataScheduled" and rule.type.startswith("new-message-")):

                            # Conduct rules only on requested folders
                            if event_data.message._schema.folder_schema in valid_folders:
                                logger.info("fired %s %s" % (rule.name, event_data.message.subject))
                                # TODO maybe user log here that event has been fired
                                is_fired = True
                                event_data.fire_event(mailbox.new_message_handler)

                    except Exception as e:
                        # Get error message for users if occurs
                        # print out error messages for user 
                        
                        # if len(inspect.trace()) < 2: 
                        #     logger.exception("System error during running user code")
                        # else:
                        
                        exc_type, exc_obj, exc_tb = sys.exc_info()
                        logger.info(e)
                        logger.debug(exc_obj)
                        # logger.info(traceback.print_exception())

                        # TODO find keyword 'in on_message' or on_flag_change
                        logger.info(traceback.format_tb(exc_tb))
                        logger.info(sys.exc_info())
                        
                        copy_msg["log"] = str(e) + traceback.format_tb(exc_tb)[-1]
                        copy_msg["error"] = True 
                    finally:         
                        if is_fired:
                            logger.debug("handling fired %s %s" % (rule.name, event_data.message.subject))
                            copy_msg["trigger"] = rule.name
                            
                            copy_msg["log"] = "%s\n%s" % (user_std_out.getvalue(), copy_msg["log"] )

                            new_log[copy_msg["timestamp"]] = copy_msg    

                        # flush buffer
                        user_std_out = StringIO()

                        # set the stdout to a string
                        sys.stdout = user_std_out

                        # set the user logger to
                        userLoggerStream = user_std_out

                    mailbox.new_message_handler.removeAllHandles()

    except Exception as e:
        res['status'] = False
        logger.exception("failure running user %s code" % mailbox._imap_account.email)
    finally:
        # set the stdout back to what it was
        sys.stdout = sys.__stdout__
        userLoggerStream = sys.__stdout__

        # if it is simulate don't save to db
        if is_simulate:
            logger.debug(res)
        
        # save logs to db
        else:
            logger.info(new_log)
            res['imap_log'] = new_log

        user_std_out.close()
        return res

    # with stdoutIO() as s:
    #     def catch_exception(e):
    #         etype, evalue = sys.exc_info()[:2]
    #         estr = traceback.format_exception_only(etype, evalue)
    #         logstr = 'Error during executing your code \n'
    #         for each in estr:
    #             logstr += '{0}; '.format(each.strip('\n'))

    #         logstr = "%s \n %s" % (logstr, str(e))

    #         # Send this error msg to the user
    #         res['imap_log'] = logstr
    #         res['imap_error'] = True

    #     def on_message_arrival(func=None):
    #         if not func or type(func).__name__ != "function":
    #             raise Exception('on_message_arrival(): requires callback function but it is %s ' % type(func).__name__)

    #         if func.func_code.co_argcount != 1:
    #             raise Exception('on_message_arrival(): your callback function should have only 1 argument, but there are %d argument(s)' % func.func_code.co_argcount)

    #         # TODO warn users if it conatins send() and their own email (i.e., it potentially leads to infinite loops)

    #         # TODO replace with the right folder
    #         current_folder_schema = FolderSchema.objects.filter(imap_account=imap_account, name="INBOX")[0]
    #         action = Action(trigger="arrival", code=codeobject_dumps(func.func_code), folder=current_folder_schema)
    #         action.save()

    #     def set_timeout(delay=None, func=None):
    #         if not delay:
    #             raise Exception('set_timeout(): requires delay (in second)')

    #         if delay < 1:
    #             raise Exception('set_timeout(): requires delay larger than 1 sec')

    #         if not func:
    #             raise Exception('set_timeout(): requires code to be executed periodically')

    #         args = ujson.dumps( [imap_account.id, marshal.dumps(func.func_code), search_creteria, is_test, email_content] )
    #         add_periodic_task.delay( delay, args, delay * 2 - 0.5 ) # make it expire right before 2nd execution happens



    #     # return a list of email UIDs
    #     def search(criteria=u'ALL', charset=None, folder=None):
    #         # TODO how to deal with folders
    #         # iterate through all the functions
    #         if folder is None:
    #             pass

    #         # iterate through a folder of list of folder
    #         else:
    #             # if it's a list iterate
    #             pass
    #             # else it's a string search a folder

    #         select_folder('INBOX')
    #         return imap.search(criteria, charset)



    #     def delete_folder(folder):
    #         pile.delete_folder(folder, is_test)

    #     def list_folders(directory=u'', pattern=u'*'):
    #         return pile.list_folders(directory, pattern)

    #     def select_folder(folder):
    #         if not imap.folder_exists(folder):
    #             logger.error("Select folder; folder %s not exist" % folder)
    #             return

    #         imap.select_folder(folder)
    #         logger.debug("Select a folder %s" % folder)

    #     def get_mode():
    #         if imap_account.current_mode:
    #             return imap_account.current_mode.uid
    #         else:
    #             return None

    #     def set_mode(mode_index):
    #         try:
    #             mode_index = int(mode_index)
    #         except ValueError:
    #             raise Exception('set_mode(): args mode_index must be a index (integer)')

    #         mm = MailbotMode.objects.filter(uid=mode_index, imap_account=imap_account)
    #         if mm.exists():
    #             mm = mm[0]
    #             if not is_test:
    #                 imap_account.current_mode = mm
    #                 imap_account.save()

    #             logger.debug("Set mail mode to %s (%d)" % (mm.name, mode_index))
    #             return True
    #         else:
    #             logger.error("A mode ID %d not exist!" % (mode_index))
    #             return False

    #     try:
    #         if is_valid:
    #             exec code in globals(), locals()
    #             pile.add_flags(['YouPS'])
    #             res['status'] = True
    #     except Action.DoesNotExist:
    #         logger.debug("An action is not existed right now. Maybe you change your script after this action was added to the queue.")
    #     except Exception as e:
    #         catch_exception(e)

    #     res['imap_log'] = s.getvalue() + res['imap_log']

    #     return res
